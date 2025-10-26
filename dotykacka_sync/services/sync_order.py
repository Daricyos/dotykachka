"""Order Synchronization Service."""

import logging
import json
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DotykackaOrderSync(models.AbstractModel):
    """Service for synchronizing orders from Dotykačka to Odoo."""

    _name = 'dotykacka.sync.order'
    _description = 'Dotykačka Order Sync Service'

    @api.model
    def sync_orders(self, config, limit=100, date_from=None, date_to=None):
        """
        Sync orders from Dotykačka to Odoo.

        Args:
            config: dotykacka.config record
            limit: Maximum number of orders to sync per batch
            date_from: Filter from date (YYYY-MM-DD)
            date_to: Filter to date (YYYY-MM-DD)

        Returns:
            dict: Sync statistics
        """
        if not config.sync_orders:
            _logger.info('Order sync is disabled for config %s', config.cloud_id)
            return {'skipped': True}

        api_client = self.env['dotykacka.api'].create_client(config)
        stats = {
            'created': 0,
            'updated': 0,
            'deleted': 0,
            'errors': 0,
            'skipped': 0,
        }

        try:
            offset = 0
            while True:
                # Fetch orders from API
                response = api_client.get_orders(
                    limit=limit,
                    offset=offset,
                    date_from=date_from,
                    date_to=date_to
                )
                orders = response.get('data', [])

                if not orders:
                    break

                for order_data in orders:
                    try:
                        result = self._sync_order(config, order_data)
                        stats[result] += 1
                    except Exception as e:
                        _logger.error('Error syncing order %s: %s', order_data.get('id'), str(e))
                        stats['errors'] += 1

                        # Log error
                        self.env['dotykacka.sync.log'].log_error(
                            config=config,
                            sync_type='order',
                            sync_action='update',
                            message=f"Failed to sync order {order_data.get('id')}",
                            error=e,
                            dotykacka_id=str(order_data.get('id')),
                            response_data=str(order_data)
                        )

                # Check if there are more orders
                if len(orders) < limit:
                    break

                offset += limit

            _logger.info('Order sync completed: %s', stats)
            return stats

        except Exception as e:
            _logger.error('Order sync failed: %s', str(e))
            raise

    def _sync_order(self, config, order_data):
        """
        Sync single order.

        Args:
            config: dotykacka.config record
            order_data: Order data from Dotykačka API

        Returns:
            str: 'created', 'updated', 'deleted', or 'skipped'
        """
        receipt_id = order_data.get('id')
        if not receipt_id:
            return 'skipped'

        # Check order status filter
        order_status = self._determine_order_status(order_data)

        if config.order_status_filter == 'on_site' and order_status == 'takeaway':
            _logger.debug('Skipping takeaway order %s (handled in KeyCRM)', receipt_id)
            return 'skipped'

        # Check if order was deleted
        if order_data.get('deleted', False):
            return self._handle_deleted_order(config, receipt_id, order_data)

        # Get or create order mapping
        mapping = self.env['dotykacka.order.mapping'].find_or_create_mapping(
            config, receipt_id, order_data
        )

        # Create or update sale order
        sale_order = self._create_or_update_sale_order(config, order_data, mapping)

        # Create invoice
        invoice = self._create_invoice(config, sale_order, order_data, mapping)

        # Create payments
        payments = self._create_payments(config, invoice, order_data, mapping)

        # Update mapping
        self.env['dotykacka.order.mapping'].update_mapping(
            mapping,
            sale_order=sale_order,
            invoice=invoice,
            payments=payments
        )

        # Determine action
        action = 'created' if not mapping.sale_order_id else 'updated'

        # Log success
        self.env['dotykacka.sync.log'].log_success(
            config=config,
            sync_type='order',
            sync_action=action,
            message=f"Order {sale_order.name} synced successfully",
            dotykacka_id=str(receipt_id),
            odoo_model='sale.order',
            odoo_id=sale_order.id,
            odoo_record_name=sale_order.name
        )

        return action

    def _determine_order_status(self, order_data):
        """
        Determine order status from order data.

        Args:
            order_data: Order data from API

        Returns:
            str: 'on_site', 'takeaway', 'delivery', or 'other'
        """
        # Check various fields that might indicate order type
        order_type = order_data.get('type', '').lower()
        delivery_method = order_data.get('deliveryMethod', '').lower()
        location = order_data.get('location', '').lower()

        if 'takeaway' in order_type or 'takeaway' in delivery_method:
            return 'takeaway'
        elif 'delivery' in order_type or 'delivery' in delivery_method:
            return 'delivery'
        elif 'table' in location or 'dine' in location:
            return 'on_site'
        else:
            return 'on_site'  # Default to on_site

    def _handle_deleted_order(self, config, receipt_id, order_data):
        """
        Handle deleted order from Dotykačka.

        Args:
            config: dotykacka.config record
            receipt_id: Receipt ID
            order_data: Order data from API

        Returns:
            str: 'deleted' or 'skipped'
        """
        mapping = self.env['dotykacka.order.mapping'].search([
            ('config_id', '=', config.id),
            ('dotykacka_receipt_id', '=', str(receipt_id)),
        ], limit=1)

        if not mapping:
            return 'skipped'

        # Cancel order
        mapping.action_cancel_order()

        # Log
        self.env['dotykacka.sync.log'].log_success(
            config=config,
            sync_type='order',
            sync_action='delete',
            message=f"Order {mapping.sale_order_id.name if mapping.sale_order_id else receipt_id} cancelled (deleted in Dotykačka)",
            dotykacka_id=str(receipt_id),
            odoo_model='sale.order',
            odoo_id=mapping.sale_order_id.id if mapping.sale_order_id else None
        )

        return 'deleted'

    def _create_or_update_sale_order(self, config, order_data, mapping):
        """
        Create or update sale order from order data.

        Args:
            config: dotykacka.config record
            order_data: Order data from API
            mapping: dotykacka.order.mapping record

        Returns:
            sale.order: Sale order record
        """
        vals = self._prepare_sale_order_vals(config, order_data)

        if mapping.sale_order_id:
            # Update existing order
            sale_order = mapping.sale_order_id
            # Only update if order is still in draft
            if sale_order.state == 'draft':
                sale_order.write(vals)
        else:
            # Create new order
            sale_order = self.env['sale.order'].create(vals)

        # Confirm order if not already confirmed
        if sale_order.state == 'draft':
            sale_order.action_confirm()

        return sale_order

    def _prepare_sale_order_vals(self, config, order_data):
        """
        Prepare sale order values from order data.

        Args:
            config: dotykacka.config record
            order_data: Order data from API

        Returns:
            dict: Sale order values
        """
        vals = {
            'dotykacka_receipt_id': str(order_data.get('id')),
            'dotykacka_order_number': order_data.get('orderNumber'),
            'dotykacka_status': self._determine_order_status(order_data),
            'dotykacka_sync_date': fields.Datetime.now(),
            'dotykacka_config_id': config.id,
            'company_id': config.company_id.id,
        }

        # Customer
        customer_id = order_data.get('customerId')
        if customer_id:
            partner = self.env['res.partner'].search([
                ('dotykacka_customer_id', '=', str(customer_id))
            ], limit=1)

            if not partner:
                # Try to sync customer
                try:
                    partner = self.env['dotykacka.sync.customer'].sync_customer_by_id(
                        config, customer_id
                    )
                except Exception as e:
                    _logger.warning('Could not sync customer %s: %s', customer_id, str(e))

            if partner:
                vals['partner_id'] = partner.id
            else:
                # Use default customer
                vals['partner_id'] = config.company_id.partner_id.id
        else:
            # Use default customer (company itself or generic walk-in customer)
            vals['partner_id'] = config.company_id.partner_id.id

        # Order date
        if order_data.get('createdAt'):
            try:
                order_date = datetime.fromisoformat(order_data['createdAt'].replace('Z', '+00:00'))
                vals['date_order'] = order_date
            except Exception:
                pass

        # Salesperson
        employee_id = order_data.get('employeeId')
        if employee_id and config.default_salesperson_id:
            # Could map employees to salespeople if needed
            vals['user_id'] = config.default_salesperson_id.id
        elif config.default_salesperson_id:
            vals['user_id'] = config.default_salesperson_id.id

        # Warehouse
        if config.default_warehouse_id:
            vals['warehouse_id'] = config.default_warehouse_id.id

        # Pricelist
        if config.default_pricelist_id:
            vals['pricelist_id'] = config.default_pricelist_id.id

        # Order lines
        vals['order_line'] = self._prepare_order_lines(config, order_data)

        # Note
        if order_data.get('note'):
            vals['note'] = order_data['note']

        return vals

    def _prepare_order_lines(self, config, order_data):
        """
        Prepare order lines from order data.

        Args:
            config: dotykacka.config record
            order_data: Order data from API

        Returns:
            list: Order line values (for create)
        """
        lines = []
        items = order_data.get('items', [])

        for item in items:
            product_id = item.get('productId')
            if not product_id:
                continue

            # Find or sync product
            product = self.env['product.product'].search([
                ('dotykacka_product_id', '=', str(product_id))
            ], limit=1)

            if not product:
                try:
                    product = self.env['dotykacka.sync.product'].sync_product_by_id(
                        config, product_id
                    )
                except Exception as e:
                    _logger.warning('Could not sync product %s: %s', product_id, str(e))
                    continue

            if not product:
                continue

            # Line values
            line_vals = {
                'product_id': product.id,
                'name': item.get('name') or product.name,
                'product_uom_qty': item.get('quantity', 1.0),
                'price_unit': item.get('priceWithVat', 0.0),
            }

            # Discount
            if item.get('discountPercent'):
                line_vals['discount'] = item['discountPercent']

            lines.append((0, 0, line_vals))

        return lines

    def _create_invoice(self, config, sale_order, order_data, mapping):
        """
        Create invoice from sale order.

        Args:
            config: dotykacka.config record
            sale_order: sale.order record
            order_data: Order data from API
            mapping: dotykacka.order.mapping record

        Returns:
            account.move: Invoice record
        """
        # Check if invoice already exists
        if mapping.invoice_id and mapping.invoice_id.state != 'cancel':
            return mapping.invoice_id

        # Create invoice from sale order
        invoice = sale_order._create_invoices()

        # Update invoice with Dotykačka data
        invoice.write({
            'dotykacka_receipt_id': str(order_data.get('id')),
            'dotykacka_sync_date': fields.Datetime.now(),
            'dotykacka_config_id': config.id,
        })

        # Post invoice
        invoice.action_post()

        return invoice

    def _create_payments(self, config, invoice, order_data, mapping):
        """
        Create payments from order data.

        Args:
            config: dotykacka.config record
            invoice: account.move record
            order_data: Order data from API
            mapping: dotykacka.order.mapping record

        Returns:
            account.payment: Payment recordset
        """
        payments = self.env['account.payment']
        payment_items = order_data.get('payments', [])

        for payment_item in payment_items:
            payment_method = payment_item.get('method', 'cash')
            amount = payment_item.get('amount', 0.0)

            if amount <= 0:
                continue

            # Get journal for payment method
            try:
                journal = self.env['dotykacka.payment.mapping'].get_journal_for_payment_method(
                    config,
                    payment_method,
                    payment_item.get('id')
                )
            except ValidationError as e:
                _logger.warning('Could not find journal for payment method %s: %s', payment_method, str(e))
                continue

            # Create payment
            payment_vals = {
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': invoice.partner_id.id,
                'amount': amount,
                'currency_id': invoice.currency_id.id,
                'journal_id': journal.id,
                'date': invoice.invoice_date or fields.Date.today(),
                'ref': f"{invoice.name} - {payment_method}",
                'dotykacka_payment_id': str(payment_item.get('id')),
                'dotykacka_receipt_id': str(order_data.get('id')),
                'dotykacka_payment_method': payment_method,
                'dotykacka_sync_date': fields.Datetime.now(),
                'dotykacka_config_id': config.id,
            }

            payment = self.env['account.payment'].create(payment_vals)

            # Post payment
            payment.action_post()

            # Reconcile with invoice
            lines = (payment.line_ids + invoice.line_ids).filtered(
                lambda l: l.account_id == invoice.partner_id.property_account_receivable_id
                and not l.reconciled
            )
            if lines:
                lines.reconcile()

            payments |= payment

        return payments

    @api.model
    def sync_order_by_id(self, config, order_id):
        """
        Sync single order by ID.

        Args:
            config: dotykacka.config record
            order_id: Order/Receipt ID in Dotykačka

        Returns:
            sale.order: Synced sale order record
        """
        api_client = self.env['dotykacka.api'].create_client(config)

        try:
            order_data = api_client.get_order(order_id)
            self._sync_order(config, order_data)

            mapping = self.env['dotykacka.order.mapping'].search([
                ('config_id', '=', config.id),
                ('dotykacka_receipt_id', '=', str(order_id)),
            ], limit=1)

            return mapping.sale_order_id if mapping else None

        except Exception as e:
            _logger.error('Failed to sync order %s: %s', order_id, str(e))
            raise ValidationError(_(
                'Failed to sync order: %s'
            ) % str(e))
