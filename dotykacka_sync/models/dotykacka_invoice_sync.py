from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DotykackaInvoiceSync(models.TransientModel):
    """Invoice synchronization for Dotykačka orders."""

    _name = 'dotykacka.invoice.sync'
    _description = 'Dotykačka Invoice Synchronization'

    config_id = fields.Many2one(
        'dotykacka.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
    )

    def create_invoice_for_order(self, order, order_data=None):
        """
        Create and optionally validate invoice for a sales order.

        Args:
            order (sale.order): Sales order
            order_data (dict): Optional order data from Dotykačka

        Returns:
            account.move: Created invoice
        """
        self.ensure_one()

        if not order:
            raise UserError(_('Order is required'))

        # Check if invoice already exists
        if order.invoice_ids.filtered(lambda inv: inv.state != 'cancel'):
            _logger.info('Invoice already exists for order %s', order.name)
            return order.invoice_ids[0]

        try:
            # Create invoice from sales order
            invoice = order._create_invoices()

            if not invoice:
                raise UserError(_('Failed to create invoice for order %s') % order.name)

            # Set Dotykačka reference
            if order.dotykacka_order_id:
                invoice.dotykacka_order_id = order.dotykacka_order_id

            if order_data and order_data.get('receiptNumber'):
                invoice.ref = order_data['receiptNumber']

            # Auto-validate if configured
            if self.config_id.auto_validate_invoice and invoice.state == 'draft':
                invoice.action_post()
                _logger.info('Invoice %s validated for order %s', invoice.name, order.name)

            # Log success
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'sync',
                'direction': 'incoming',
                'endpoint': 'invoice_creation',
                'status_code': 200,
                'order_id': order.id,
                'invoice_id': invoice.id,
                'response_data': f'Invoice {invoice.name} created for order {order.name}',
            })

            return invoice

        except Exception as e:
            _logger.error('Failed to create invoice for order %s: %s', order.name, str(e))

            # Log error
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'error',
                'direction': 'incoming',
                'endpoint': 'invoice_creation',
                'status_code': 0,
                'order_id': order.id,
                'error_message': str(e),
            })

            raise

    def cancel_invoice(self, invoice):
        """
        Cancel an invoice (set to draft then cancel).

        Args:
            invoice (account.move): Invoice to cancel
        """
        self.ensure_one()

        if not invoice:
            return

        try:
            if invoice.state == 'posted':
                # Reset to draft
                invoice.button_draft()

            if invoice.state == 'draft':
                # Cancel the invoice
                invoice.button_cancel()

            _logger.info('Cancelled invoice %s', invoice.name)

            # Log success
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'sync',
                'direction': 'incoming',
                'endpoint': 'invoice_cancellation',
                'status_code': 200,
                'invoice_id': invoice.id,
                'response_data': f'Invoice {invoice.name} cancelled',
            })

        except Exception as e:
            _logger.error('Failed to cancel invoice %s: %s', invoice.name, str(e))

            # Log error
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'error',
                'direction': 'incoming',
                'endpoint': 'invoice_cancellation',
                'status_code': 0,
                'invoice_id': invoice.id,
                'error_message': str(e),
            })

            raise
