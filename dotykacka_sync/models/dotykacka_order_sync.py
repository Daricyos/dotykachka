from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class DotykackaOrderSync(models.TransientModel):
    """Sales order synchronization from Dotykačka to Odoo."""

    _name = 'dotykacka.order.sync'
    _description = 'Dotykačka Order Synchronization'

    config_id = fields.Many2one(
        'dotykacka.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
    )

    def _get_oauth(self):
        """Get OAuth handler for API calls."""
        return self.env['dotykacka.oauth'].create({'config_id': self.config_id.id})

    def sync_order(self, order_data, force=False):
        """
        Sync a single order from Dotykačka to Odoo.

        Args:
            order_data (dict): Order data from Dotykačka API
            force (bool): Force sync even if filters don't match

        Returns:
            sale.order: Odoo sales order record
        """
        self.ensure_one()

        dotykacka_id = str(order_data.get('id'))
        if not dotykacka_id:
            _logger.warning('Order data missing ID: %s', order_data)
            return None

        # Apply order status filter
        if not force and not self._should_sync_order(order_data):
            _logger.info('Skipping order %s (filtered out)', dotykacka_id)
            return None

        # Check if order already exists
        order = self.env['sale.order'].search([
            ('dotykacka_order_id', '=', dotykacka_id),
            ('company_id', '=', self.config_id.company_id.id),
        ], limit=1)

        try:
            # Fetch full order details if needed
            if not order_data.get('items'):
                order_data = self._fetch_order_details(dotykacka_id)

            # Prepare order values
            order_vals = self._prepare_order_vals(order_data)

            if order:
                # Update existing order
                self._update_order(order, order_vals, order_data)
                _logger.info('Updated order %s (Dotykačka ID: %s)', order.name, dotykacka_id)
            else:
                # Create new order
                order_vals['dotykacka_order_id'] = dotykacka_id
                order = self.env['sale.order'].create(order_vals)
                _logger.info('Created order %s (Dotykačka ID: %s)', order.name, dotykacka_id)

            # Create order lines
            self._sync_order_lines(order, order_data)

            # Confirm order if needed
            if order.state == 'draft':
                order.action_confirm()

            # Process invoice if configured
            if self.config_id.auto_create_invoice:
                invoice_sync = self.env['dotykacka.invoice.sync'].create({
                    'config_id': self.config_id.id,
                })
                invoice_sync.create_invoice_for_order(order, order_data)

            # Process payments if configured
            if self.config_id.auto_reconcile_payments and order_data.get('payments'):
                payment_sync = self.env['dotykacka.payment.sync'].create({
                    'config_id': self.config_id.id,
                })
                payment_sync.sync_order_payments(order, order_data)

            # Log success
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'sync',
                'direction': 'incoming',
                'endpoint': 'order_sync',
                'status_code': 200,
                'order_id': order.id,
                'response_data': f'Order {order.name} synced successfully',
            })

            return order

        except Exception as e:
            _logger.error('Failed to sync order %s: %s', dotykacka_id, str(e))

            # Log error
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'error',
                'direction': 'incoming',
                'endpoint': 'order_sync',
                'status_code': 0,
                'error_message': str(e),
                'request_data': str(order_data),
            })

            raise

    def _should_sync_order(self, order_data):
        """
        Check if order should be synced based on configuration filters.

        Args:
            order_data (dict): Order data from Dotykačka

        Returns:
            bool: True if order should be synced
        """
        # Check order status filter
        if self.config_id.order_status_filter == 'on_site':
            # Only sync orders with status "on site"
            is_takeaway = order_data.get('isTakeaway', False)
            is_delivery = order_data.get('isDelivery', False)
            if is_takeaway or is_delivery:
                return False
        elif self.config_id.order_status_filter == 'takeaway':
            # Only sync takeaway orders
            if not order_data.get('isTakeaway', False):
                return False

        return True

    def _fetch_order_details(self, dotykacka_order_id):
        """
        Fetch full order details from Dotykačka API.

        Args:
            dotykacka_order_id (str): Dotykačka order ID

        Returns:
            dict: Full order data
        """
        oauth = self._get_oauth()
        endpoint = f'/v2/clouds/{self.config_id.cloud_id}/orders/{dotykacka_order_id}'
        return oauth.call_api('GET', endpoint)

    def _prepare_order_vals(self, order_data):
        """
        Prepare sales order values from Dotykačka order data.

        Args:
            order_data (dict): Order data from Dotykačka

        Returns:
            dict: Sales order values for create/write
        """
        vals = {
            'company_id': self.config_id.company_id.id,
        }

        # Customer
        customer_id = order_data.get('customerId')
        if customer_id:
            partner = self._get_or_sync_customer(customer_id)
            if partner:
                vals['partner_id'] = partner.id

        # If no customer, use default POS customer
        if not vals.get('partner_id'):
            vals['partner_id'] = self._get_default_customer().id

        # Order reference
        if order_data.get('receiptNumber'):
            vals['client_order_ref'] = order_data['receiptNumber']

        # Salesperson
        if order_data.get('employeeId'):
            salesperson = self._find_salesperson(order_data['employeeId'])
            if salesperson:
                vals['user_id'] = salesperson.id

        # Order date
        if order_data.get('createdAt'):
            try:
                vals['date_order'] = datetime.fromisoformat(
                    order_data['createdAt'].replace('Z', '+00:00')
                )
            except (ValueError, AttributeError):
                pass

        # Note
        if order_data.get('note'):
            vals['note'] = order_data['note']

        # Dotykačka metadata
        vals['dotykacka_receipt_number'] = order_data.get('receiptNumber')
        vals['dotykacka_is_takeaway'] = order_data.get('isTakeaway', False)
        vals['dotykacka_is_delivery'] = order_data.get('isDelivery', False)

        return vals

    def _update_order(self, order, order_vals, order_data):
        """
        Update existing sales order.

        Args:
            order (sale.order): Existing order
            order_vals (dict): New values
            order_data (dict): Full order data from Dotykačka
        """
        # Don't update cancelled/done orders
        if order.state in ['cancel', 'done']:
            _logger.info('Skipping update of order %s (state: %s)', order.name, order.state)
            return

        # Update order
        order.write(order_vals)

    def _sync_order_lines(self, order, order_data):
        """
        Synchronize order lines from Dotykačka order data.

        Args:
            order (sale.order): Odoo sales order
            order_data (dict): Order data from Dotykačka
        """
        items = order_data.get('items', [])
        if not items:
            _logger.warning('No items found in order %s', order_data.get('id'))
            return

        # Clear existing order lines if updating
        if order.order_line:
            order.order_line.unlink()

        # Create new order lines
        for item_data in items:
            self._create_order_line(order, item_data)

    def _create_order_line(self, order, item_data):
        """
        Create a single order line from Dotykačka item data.

        Args:
            order (sale.order): Odoo sales order
            item_data (dict): Item data from Dotykačka
        """
        # Get or sync product
        product_id = item_data.get('productId')
        if not product_id:
            _logger.warning('Item missing productId: %s', item_data)
            return

        product = self._get_or_sync_product(product_id)
        if not product:
            _logger.error('Failed to get product for item: %s', item_data)
            return

        # Prepare line values
        line_vals = {
            'order_id': order.id,
            'product_id': product.id,
            'name': product.name,
            'product_uom_qty': float(item_data.get('quantity', 1.0)),
            'product_uom': product.uom_id.id,
        }

        # Price
        if item_data.get('priceWithVat'):
            line_vals['price_unit'] = float(item_data['priceWithVat'])
        elif item_data.get('unitPrice'):
            line_vals['price_unit'] = float(item_data['unitPrice'])
        else:
            line_vals['price_unit'] = product.list_price

        # Discount
        if item_data.get('discountPercent'):
            line_vals['discount'] = float(item_data['discountPercent'])

        # Tax
        if item_data.get('vatRate'):
            vat_rate = float(item_data['vatRate'])
            tax = self._find_or_create_tax(vat_rate)
            if tax:
                line_vals['tax_id'] = [(6, 0, [tax.id])]

        # Create order line
        self.env['sale.order.line'].create(line_vals)

    def _get_or_sync_customer(self, dotykacka_customer_id):
        """
        Get customer from Odoo or sync from Dotykačka.

        Args:
            dotykacka_customer_id (str): Dotykačka customer ID

        Returns:
            res.partner: Customer record
        """
        # Try to find existing customer
        partner = self.env['res.partner'].search([
            ('dotykacka_customer_id', '=', str(dotykacka_customer_id)),
            ('company_id', '=', self.config_id.company_id.id),
        ], limit=1)

        if not partner and self.config_id.sync_customers:
            # Sync customer from Dotykačka
            try:
                customer_sync = self.env['dotykacka.customer.sync'].create({
                    'config_id': self.config_id.id,
                })
                partner = customer_sync.sync_customer_by_id(str(dotykacka_customer_id))
            except Exception as e:
                _logger.error('Failed to sync customer %s: %s', dotykacka_customer_id, str(e))

        return partner

    def _get_or_sync_product(self, dotykacka_product_id):
        """
        Get product from Odoo or sync from Dotykačka.

        Args:
            dotykacka_product_id (str): Dotykačka product ID

        Returns:
            product.product: Product record
        """
        # Try to find existing product
        product = self.env['product.product'].search([
            ('dotykacka_product_id', '=', str(dotykacka_product_id)),
        ], limit=1)

        if not product and self.config_id.sync_products:
            # Sync product from Dotykačka
            try:
                product_sync = self.env['dotykacka.product.sync'].create({
                    'config_id': self.config_id.id,
                })
                product = product_sync.sync_product_by_id(str(dotykacka_product_id))
            except Exception as e:
                _logger.error('Failed to sync product %s: %s', dotykacka_product_id, str(e))

        return product

    def _get_default_customer(self):
        """Get default POS customer."""
        partner = self.env['res.partner'].search([
            ('name', '=', 'POS Customer'),
            ('company_id', '=', self.config_id.company_id.id),
        ], limit=1)

        if not partner:
            partner = self.env['res.partner'].create({
                'name': 'POS Customer',
                'company_id': self.config_id.company_id.id,
                'customer_rank': 1,
            })

        return partner

    def _find_salesperson(self, employee_id):
        """
        Find Odoo user by Dotykačka employee ID.

        Args:
            employee_id (str): Dotykačka employee ID

        Returns:
            res.users: User record or None
        """
        # This would need custom mapping logic
        # For now, return None
        return None

    def _find_or_create_tax(self, vat_rate):
        """Find or create tax with given VAT rate."""
        tax = self.env['account.tax'].search([
            ('amount', '=', vat_rate),
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', self.config_id.company_id.id),
        ], limit=1)

        if not tax:
            tax = self.env['account.tax'].create({
                'name': f'VAT {vat_rate}%',
                'amount': vat_rate,
                'type_tax_use': 'sale',
                'company_id': self.config_id.company_id.id,
            })

        return tax

    def sync_recent_orders(self, days=7, limit=None):
        """
        Sync recent orders from Dotykačka.

        Args:
            days (int): Number of days to look back
            limit (int): Optional limit on number of orders
        """
        self.ensure_one()

        if not self.config_id.sync_orders:
            _logger.info('Order sync is disabled for config %s', self.config_id.cloud_name)
            return

        oauth = self._get_oauth()
        endpoint = f'/v2/clouds/{self.config_id.cloud_id}/orders'

        # Calculate date filter
        from_date = (datetime.now() - timedelta(days=days)).isoformat()
        params = {
            'createdSince': from_date,
        }

        try:
            synced_count = 0
            error_count = 0
            skipped_count = 0

            # Fetch orders using pagination
            for order_data in oauth.call_api_paginated('GET', endpoint, params=params):
                try:
                    # Check if should sync
                    if not self._should_sync_order(order_data):
                        skipped_count += 1
                        continue

                    self.sync_order(order_data)
                    synced_count += 1

                    if limit and synced_count >= limit:
                        break

                except Exception as e:
                    error_count += 1
                    _logger.error('Failed to sync order: %s', str(e))
                    continue

            _logger.info(
                'Order sync completed: %d synced, %d skipped, %d errors',
                synced_count, skipped_count, error_count
            )

            return {
                'synced': synced_count,
                'skipped': skipped_count,
                'errors': error_count,
            }

        except Exception as e:
            _logger.error('Order sync failed: %s', str(e))
            raise UserError(_('Order synchronization failed: %s') % str(e))

    def handle_order_deletion(self, dotykacka_order_id):
        """
        Handle order deletion from Dotykačka.

        Args:
            dotykacka_order_id (str): Dotykačka order ID
        """
        self.ensure_one()

        # Find the order
        order = self.env['sale.order'].search([
            ('dotykacka_order_id', '=', str(dotykacka_order_id)),
            ('company_id', '=', self.config_id.company_id.id),
        ], limit=1)

        if not order:
            _logger.warning('Order %s not found for deletion', dotykacka_order_id)
            return

        try:
            # Cancel related invoices
            if order.invoice_ids:
                for invoice in order.invoice_ids.filtered(lambda i: i.state == 'posted'):
                    invoice.button_draft()
                    invoice.button_cancel()

            # Cancel related payments
            payments = self.env['account.payment'].search([
                ('dotykacka_order_id', '=', str(dotykacka_order_id)),
            ])
            for payment in payments.filtered(lambda p: p.state == 'posted'):
                payment.action_draft()
                payment.action_cancel()

            # Cancel the order
            if order.state != 'cancel':
                order.action_cancel()

            _logger.info('Cancelled order %s and related records', order.name)

            # Log the deletion
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'sync',
                'direction': 'incoming',
                'endpoint': 'order_deletion',
                'status_code': 200,
                'order_id': order.id,
                'response_data': f'Order {order.name} cancelled successfully',
            })

        except Exception as e:
            _logger.error('Failed to handle order deletion %s: %s', dotykacka_order_id, str(e))
            raise


from datetime import timedelta
