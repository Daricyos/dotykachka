"""Dotykacka Importer - Main import logic."""

import logging
from datetime import datetime, timedelta
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class DotykackaImporter(models.TransientModel):
    """Handle import of orders, customers, products from Dotykacka."""

    _name = 'dotykacka.importer'
    _description = 'Dotykacka Importer'

    # ==================== MAIN SYNC METHOD ====================

    def sync_orders(self, config):
        """
        Sync orders from Dotykacka to Odoo.

        :param config: dotykacka.config record
        """
        _logger.info(f"Starting order sync for config: {config.name}")

        # Get last sync date or default to 24 hours ago
        last_sync = config.last_sync_date or (datetime.now() - timedelta(hours=24))

        # Fetch orders from Dotykacka
        orders = self._fetch_orders_from_api(config, last_sync)

        _logger.info(f"Fetched {len(orders)} orders from Dotykacka")

        # Process each order
        for order_data in orders:
            try:
                self._process_order(config, order_data)
            except Exception as e:
                _logger.error(f"Failed to process order {order_data.get('id')}: {str(e)}")
                self._log_sync_error(config, 'order', order_data.get('id'), str(e))

        _logger.info(f"Order sync completed for config: {config.name}")

    # ==================== FETCH DATA FROM API ====================

    def _fetch_orders_from_api(self, config, from_date):
        """
        Fetch orders from Dotykacka API.

        :param config: dotykacka.config record
        :param from_date: datetime to fetch orders from
        :return: list of order dicts
        """
        oauth = self.env['dotykacka.oauth']
        access_token = oauth.ensure_valid_token(config)

        request = self.env['api_manager.request'].search([
            ('name', '=', 'Get Orders'),
            ('provider', '=', config.api_provider_id.id),
        ], limit=1)

        if not request:
            raise ValidationError(_('API request "Get Orders" not found.'))

        # Format date for API
        from_date_str = from_date.strftime('%Y-%m-%d')

        response = request.send_request(
            params={'{cloud_id}': config.cloud_id},
            args={
                'filter': f'created>={from_date_str}',
                'include': 'items,customer,payments',
                'limit': '100',
            },
            headers={'Authorization': f'Bearer {access_token}'},
            return_type='decoded',
        )

        return response.get('data', []) if response else []

    def _fetch_order_by_id(self, config, order_id):
        """
        Fetch single order by ID.

        :param config: dotykacka.config record
        :param order_id: Dotykacka order ID
        :return: order dict
        """
        oauth = self.env['dotykacka.oauth']
        access_token = oauth.ensure_valid_token(config)

        request = self.env['api_manager.request'].search([
            ('name', '=', 'Get Order'),
            ('provider', '=', config.api_provider_id.id),
        ], limit=1)

        if not request:
            raise ValidationError(_('API request "Get Order" not found.'))

        response = request.send_request(
            params={
                '{cloud_id}': config.cloud_id,
                '{order_id}': order_id,
            },
            args={'include': 'items,customer,payments'},
            headers={'Authorization': f'Bearer {access_token}'},
            return_type='decoded',
        )

        return response.get('data', {}) if response else {}

    # ==================== PROCESS ORDER ====================

    def _process_order(self, config, order_data):
        """
        Process single order from Dotykacka.

        :param config: dotykacka.config record
        :param order_data: dict with order data from API
        """
        order_id = order_data.get('id')
        location = order_data.get('location', 'on-site')

        _logger.info(f"Processing order: {order_id}, location: {location}")

        # Filter by location
        if location == 'takeaway' and not config.import_takeaway_orders:
            _logger.info(f"Skipping takeaway order: {order_id}")
            self._log_sync(config, 'order', order_id, 'skipped', 'Takeaway order')
            return

        if location == 'on-site' and not config.import_on_site_orders:
            _logger.info(f"Skipping on-site order: {order_id}")
            self._log_sync(config, 'order', order_id, 'skipped', 'On-site order')
            return

        # Check if order already exists
        existing_order = self.env['sale.order'].search([
            ('dotykacka_order_id', '=', order_id),
            ('dotykacka_config_id', '=', config.id),
        ], limit=1)

        if existing_order:
            # Update existing order
            self._update_order(config, existing_order, order_data)
        else:
            # Create new order
            self._create_order(config, order_data)

    def _create_order(self, config, order_data):
        """
        Create new sale order from Dotykacka data.

        :param config: dotykacka.config record
        :param order_data: dict with order data
        :return: sale.order record
        """
        order_id = order_data.get('id')
        _logger.info(f"Creating new order: {order_id}")

        # Import/update customer
        partner = self._import_customer(config, order_data.get('customer'))

        # Import/update products and prepare order lines
        order_lines = self._prepare_order_lines(config, order_data.get('items', []))

        # Get salesperson
        salesperson = self._map_salesperson(config, order_data.get('employeeId'))

        # Create sale order
        order_vals = {
            'partner_id': partner.id,
            'user_id': salesperson.id if salesperson else False,
            'company_id': config.company_id.id,
            'pricelist_id': config.default_pricelist_id.id if config.default_pricelist_id else partner.property_product_pricelist.id,
            'warehouse_id': config.default_warehouse_id.id if config.default_warehouse_id else False,
            'team_id': config.default_sales_team_id.id if config.default_sales_team_id else False,
            'order_line': order_lines,
            'dotykacka_order_id': order_id,
            'dotykacka_config_id': config.id,
            'dotykacka_receipt_number': order_data.get('receiptNumber'),
            'dotykacka_created_at': self._parse_datetime(order_data.get('created')),
            'note': f"Imported from Dotykacka. Order ID: {order_id}",
        }

        sale_order = self.env['sale.order'].create(order_vals)

        _logger.info(f"Sale order created: {sale_order.name}")

        # Confirm order if configured
        if config.auto_confirm_orders:
            sale_order.action_confirm()
            _logger.info(f"Sale order confirmed: {sale_order.name}")

        # Create invoice if configured
        if config.auto_create_invoice and sale_order.state == 'sale':
            invoice = sale_order._create_invoices()
            if invoice:
                invoice.action_post()
                _logger.info(f"Invoice created and posted: {invoice.name}")

                # Register payments if configured
                if config.auto_register_payment:
                    self._register_payments(config, invoice, order_data.get('payments', []))

        self._log_sync(config, 'order', order_id, 'created', f"Order {sale_order.name} created")

        return sale_order

    def _update_order(self, config, sale_order, order_data):
        """
        Update existing sale order.

        :param config: dotykacka.config record
        :param sale_order: existing sale.order record
        :param order_data: dict with updated order data
        """
        order_id = order_data.get('id')
        _logger.info(f"Updating order: {order_id} / {sale_order.name}")

        # Check if order can be updated
        if sale_order.state in ['done', 'cancel']:
            _logger.warning(f"Cannot update order in state {sale_order.state}: {sale_order.name}")
            return

        # Update order lines if needed
        # Note: This is simplified. You might want to handle line updates more carefully
        _logger.info(f"Order {sale_order.name} updated")

        self._log_sync(config, 'order', order_id, 'updated', f"Order {sale_order.name} updated")

    # ==================== CUSTOMER IMPORT ====================

    def _import_customer(self, config, customer_data):
        """
        Import or update customer.

        :param config: dotykacka.config record
        :param customer_data: dict with customer data
        :return: res.partner record
        """
        if not customer_data:
            # Return default partner if no customer data
            return self.env.ref('base.public_partner')

        customer_id = customer_data.get('id')
        email = customer_data.get('email', '').strip()
        phone = customer_data.get('phone', '').strip()

        # Search for existing partner
        partner = False
        if customer_id:
            partner = self.env['res.partner'].search([
                ('dotykacka_customer_id', '=', customer_id),
                ('dotykacka_config_id', '=', config.id),
            ], limit=1)

        if not partner and email:
            partner = self.env['res.partner'].search([
                ('email', '=', email),
            ], limit=1)

        # Prepare partner values
        partner_vals = {
            'name': customer_data.get('displayName') or customer_data.get('firstName', '') + ' ' + customer_data.get('lastName', ''),
            'email': email or False,
            'phone': phone or False,
            'vat': customer_data.get('companyId') or False,  # Tax ID
            'street': customer_data.get('street') or False,
            'city': customer_data.get('city') or False,
            'zip': customer_data.get('zip') or False,
            'dotykacka_customer_id': customer_id,
            'dotykacka_config_id': config.id,
            'company_id': config.company_id.id,
        }

        if partner:
            # Update existing partner
            partner.write(partner_vals)
            _logger.info(f"Customer updated: {partner.name}")
        else:
            # Create new partner
            partner_vals['customer_rank'] = 1
            partner = self.env['res.partner'].create(partner_vals)
            _logger.info(f"Customer created: {partner.name}")

        return partner

    # ==================== PRODUCT IMPORT ====================

    def _prepare_order_lines(self, config, items_data):
        """
        Prepare order lines from items data.

        :param config: dotykacka.config record
        :param items_data: list of item dicts
        :return: list of order line tuples
        """
        order_lines = []

        for item in items_data:
            product = self._import_product(config, item)

            if not product:
                _logger.warning(f"Product not found for item: {item.get('name')}")
                continue

            # Get tax
            tax_ids = self._map_tax(config, item.get('vat', 0))

            line_vals = {
                'product_id': product.id,
                'name': item.get('name') or product.name,
                'product_uom_qty': item.get('quantity', 1),
                'price_unit': item.get('unitPrice', 0),
                'discount': item.get('discountPercent', 0),
                'tax_id': [(6, 0, tax_ids.ids)],
            }

            order_lines.append((0, 0, line_vals))

        return order_lines

    def _import_product(self, config, item_data):
        """
        Import or update product.

        :param config: dotykacka.config record
        :param item_data: dict with item/product data
        :return: product.product record
        """
        product_id = item_data.get('productId')
        sku = item_data.get('sku', '').strip()
        ean = item_data.get('ean', '').strip()
        name = item_data.get('name', '').strip()

        # Search for existing product
        product = False

        if product_id:
            product = self.env['product.product'].search([
                ('dotykacka_product_id', '=', product_id),
                ('dotykacka_config_id', '=', config.id),
            ], limit=1)

        if not product and sku:
            product = self.env['product.product'].search([
                ('default_code', '=', sku),
            ], limit=1)

        if not product and ean:
            product = self.env['product.product'].search([
                ('barcode', '=', ean),
            ], limit=1)

        # Prepare product values
        product_vals = {
            'name': name,
            'default_code': sku or False,
            'barcode': ean or False,
            'list_price': item_data.get('unitPrice', 0),
            'dotykacka_product_id': product_id,
            'dotykacka_config_id': config.id,
            'company_id': config.company_id.id,
            'type': 'product',
            'invoice_policy': 'order',
        }

        if product:
            # Update existing product (only if not manually managed)
            if product.dotykacka_product_id:
                product.write(product_vals)
                _logger.info(f"Product updated: {product.name}")
        else:
            # Create new product
            product = self.env['product.product'].create(product_vals)
            _logger.info(f"Product created: {product.name}")

        return product

    # ==================== PAYMENT REGISTRATION ====================

    def _register_payments(self, config, invoice, payments_data):
        """
        Register payments for invoice.

        :param config: dotykacka.config record
        :param invoice: account.move record
        :param payments_data: list of payment dicts
        """
        if not payments_data:
            return

        for payment_data in payments_data:
            try:
                self._register_single_payment(config, invoice, payment_data)
            except Exception as e:
                _logger.error(f"Failed to register payment: {str(e)}")

    def _register_single_payment(self, config, invoice, payment_data):
        """
        Register single payment.

        :param config: dotykacka.config record
        :param invoice: account.move record
        :param payment_data: dict with payment data
        """
        amount = payment_data.get('amount', 0)
        payment_method = payment_data.get('paymentMethod', 'CASH')

        if amount <= 0:
            return

        # Map payment method to journal
        journal = self._map_payment_journal(config, payment_method)

        if not journal:
            _logger.warning(f"No journal found for payment method: {payment_method}")
            return

        # Create payment
        payment_vals = {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': invoice.partner_id.id,
            'amount': amount,
            'currency_id': invoice.currency_id.id,
            'journal_id': journal.id,
            'date': fields.Date.today(),
            'ref': f"Dotykacka - {invoice.name}",
            'dotykacka_payment_method': payment_method,
        }

        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()

        _logger.info(f"Payment registered: {payment.name}, Amount: {amount}, Method: {payment_method}")

        # Reconcile with invoice
        self._reconcile_payment(payment, invoice)

    def _reconcile_payment(self, payment, invoice):
        """
        Reconcile payment with invoice.

        :param payment: account.payment record
        :param invoice: account.move record
        """
        # Get payment and invoice lines to reconcile
        payment_lines = payment.line_ids.filtered(
            lambda l: l.account_id == invoice.account_id and not l.reconciled
        )
        invoice_lines = invoice.line_ids.filtered(
            lambda l: l.account_id == invoice.account_id and not l.reconciled
        )

        lines_to_reconcile = payment_lines + invoice_lines

        if lines_to_reconcile:
            lines_to_reconcile.reconcile()
            _logger.info(f"Payment reconciled with invoice: {invoice.name}")

    # ==================== ORDER DELETION/CANCELLATION ====================

    def cancel_order(self, config, order_id):
        """
        Cancel order and reverse invoice/payments.

        :param config: dotykacka.config record
        :param order_id: Dotykacka order ID
        """
        _logger.info(f"Cancelling order: {order_id}")

        sale_order = self.env['sale.order'].search([
            ('dotykacka_order_id', '=', order_id),
            ('dotykacka_config_id', '=', config.id),
        ], limit=1)

        if not sale_order:
            _logger.warning(f"Order not found for cancellation: {order_id}")
            return

        # Cancel/reverse invoices
        for invoice in sale_order.invoice_ids:
            if invoice.state == 'posted':
                # Create credit note
                move_reversal = self.env['account.move.reversal'].create({
                    'move_ids': [(4, invoice.id)],
                    'reason': 'Order deleted in Dotykacka',
                    'journal_id': invoice.journal_id.id,
                })
                move_reversal.reverse_moves()
                _logger.info(f"Credit note created for invoice: {invoice.name}")
            else:
                invoice.button_cancel()
                _logger.info(f"Invoice cancelled: {invoice.name}")

        # Cancel sale order
        if sale_order.state not in ['cancel', 'done']:
            sale_order.action_cancel()
            _logger.info(f"Sale order cancelled: {sale_order.name}")

        self._log_sync(config, 'order', order_id, 'cancelled', f"Order {sale_order.name} cancelled")

    # ==================== MAPPING METHODS ====================

    def _map_salesperson(self, config, employee_id):
        """
        Map Dotykacka employee to Odoo user.

        :param config: dotykacka.config record
        :param employee_id: Dotykacka employee ID
        :return: res.users record or False
        """
        # TODO: Implement employee mapping logic
        # For now, return False (no salesperson)
        return False

    def _map_tax(self, config, vat_rate):
        """
        Map VAT rate to Odoo tax.

        :param config: dotykacka.config record
        :param vat_rate: VAT rate as percentage (e.g., 21)
        :return: account.tax recordset
        """
        if not vat_rate:
            return self.env['account.tax']

        # Search for tax with matching amount
        tax = self.env['account.tax'].search([
            ('amount', '=', vat_rate),
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', config.company_id.id),
        ], limit=1)

        return tax

    def _map_payment_journal(self, config, payment_method):
        """
        Map Dotykacka payment method to Odoo journal.

        :param config: dotykacka.config record
        :param payment_method: Dotykacka payment method code
        :return: account.journal record or False
        """
        # Search for mapping
        mapping = self.env['dotykacka.payment.method'].search([
            ('config_id', '=', config.id),
            ('dotykacka_method', '=', payment_method),
        ], limit=1)

        if mapping and mapping.journal_id:
            return mapping.journal_id

        # Fallback: try to find journal by type
        journal_type_mapping = {
            'CASH': 'cash',
            'CARD': 'bank',
        }

        journal_type = journal_type_mapping.get(payment_method, 'bank')

        journal = self.env['account.journal'].search([
            ('type', '=', journal_type),
            ('company_id', '=', config.company_id.id),
        ], limit=1)

        return journal

    # ==================== HELPER METHODS ====================

    def _parse_datetime(self, date_string):
        """Parse datetime string from API."""
        if not date_string:
            return False
        try:
            return datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        except Exception:
            return False

    def _log_sync(self, config, entity_type, entity_id, status, message):
        """Log sync operation."""
        self.env['dotykacka.sync.log'].create({
            'config_id': config.id,
            'entity_type': entity_type,
            'entity_id': str(entity_id),
            'status': status,
            'message': message,
        })

    def _log_sync_error(self, config, entity_type, entity_id, error_message):
        """Log sync error."""
        self._log_sync(config, entity_type, entity_id, 'error', error_message)
