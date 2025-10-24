from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DotykackaPaymentSync(models.TransientModel):
    """Payment synchronization for Dotykačka orders."""

    _name = 'dotykacka.payment.sync'
    _description = 'Dotykačka Payment Synchronization'

    config_id = fields.Many2one(
        'dotykacka.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
    )

    def sync_order_payments(self, order, order_data):
        """
        Sync payments for an order from Dotykačka.

        Args:
            order (sale.order): Sales order
            order_data (dict): Order data from Dotykačka API

        Returns:
            list: List of created payment records
        """
        self.ensure_one()

        if not order or not order_data:
            return []

        payments_data = order_data.get('payments', [])
        if not payments_data:
            _logger.warning('No payments found in order %s', order.dotykacka_order_id)
            return []

        created_payments = []

        for payment_data in payments_data:
            try:
                payment = self._create_payment(order, payment_data)
                if payment:
                    created_payments.append(payment)
            except Exception as e:
                _logger.error('Failed to create payment: %s', str(e))
                continue

        # Reconcile payments to invoice if configured
        if self.config_id.auto_reconcile_payments and created_payments:
            self._reconcile_payments(order, created_payments)

        return created_payments

    def _create_payment(self, order, payment_data):
        """
        Create a payment record from Dotykačka payment data.

        Args:
            order (sale.order): Sales order
            payment_data (dict): Payment data from Dotykačka

        Returns:
            account.payment: Created payment record
        """
        # Get payment method mapping
        payment_method_id = str(payment_data.get('paymentMethodId'))
        journal = self.env['dotykacka.payment.method'].get_journal_for_payment(
            payment_method_id,
            self.config_id.id
        )

        if not journal:
            _logger.warning(
                'No journal mapping found for payment method %s',
                payment_method_id
            )
            # Get default journal
            journal = self._get_default_journal()

        if not journal:
            raise UserError(_('No payment journal configured'))

        # Get invoice
        invoice = order.invoice_ids.filtered(
            lambda inv: inv.state == 'posted' and inv.move_type == 'out_invoice'
        )
        if not invoice:
            _logger.warning('No posted invoice found for order %s', order.name)
            return None

        invoice = invoice[0]  # Take the first invoice

        # Prepare payment values
        payment_vals = {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': order.partner_id.id,
            'amount': float(payment_data.get('amount', 0.0)),
            'journal_id': journal.id,
            'date': order.date_order.date() if order.date_order else fields.Date.today(),
            'ref': f"{order.name} - {payment_data.get('paymentMethodName', 'Payment')}",
            'company_id': self.config_id.company_id.id,
        }

        # Dotykačka metadata
        payment_vals['dotykacka_order_id'] = order.dotykacka_order_id
        payment_vals['dotykacka_payment_method_id'] = payment_method_id
        payment_vals['dotykacka_payment_method_name'] = payment_data.get('paymentMethodName', '')

        try:
            # Create payment
            payment = self.env['account.payment'].create(payment_vals)

            # Post the payment
            payment.action_post()

            _logger.info(
                'Created payment %s for order %s (amount: %s)',
                payment.name, order.name, payment.amount
            )

            # Log success
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'sync',
                'direction': 'incoming',
                'endpoint': 'payment_creation',
                'status_code': 200,
                'order_id': order.id,
                'payment_id': payment.id,
                'response_data': f'Payment {payment.name} created for order {order.name}',
            })

            return payment

        except Exception as e:
            _logger.error('Failed to create payment for order %s: %s', order.name, str(e))

            # Log error
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'error',
                'direction': 'incoming',
                'endpoint': 'payment_creation',
                'status_code': 0,
                'order_id': order.id,
                'error_message': str(e),
                'request_data': str(payment_data),
            })

            raise

    def _reconcile_payments(self, order, payments):
        """
        Reconcile payments to invoice.

        Args:
            order (sale.order): Sales order
            payments (list): List of account.payment records
        """
        invoice = order.invoice_ids.filtered(
            lambda inv: inv.state == 'posted' and inv.move_type == 'out_invoice'
        )

        if not invoice:
            _logger.warning('No posted invoice found for reconciliation')
            return

        invoice = invoice[0]

        try:
            # Get invoice receivable line
            invoice_lines = invoice.line_ids.filtered(
                lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled
            )

            # Get payment lines
            payment_lines = self.env['account.move.line']
            for payment in payments:
                if payment.state == 'posted':
                    payment_lines |= payment.line_ids.filtered(
                        lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled
                    )

            # Reconcile
            if invoice_lines and payment_lines:
                (invoice_lines + payment_lines).reconcile()
                _logger.info('Reconciled payments to invoice %s', invoice.name)

                # Log success
                self.env['dotykacka.sync.log'].create({
                    'config_id': self.config_id.id,
                    'log_type': 'sync',
                    'direction': 'incoming',
                    'endpoint': 'payment_reconciliation',
                    'status_code': 200,
                    'order_id': order.id,
                    'invoice_id': invoice.id,
                    'response_data': f'Payments reconciled to invoice {invoice.name}',
                })

        except Exception as e:
            _logger.error('Failed to reconcile payments for order %s: %s', order.name, str(e))

            # Log error (but don't raise - reconciliation is not critical)
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'error',
                'direction': 'incoming',
                'endpoint': 'payment_reconciliation',
                'status_code': 0,
                'order_id': order.id,
                'invoice_id': invoice.id,
                'error_message': str(e),
            })

    def _get_default_journal(self):
        """Get default payment journal (cash or bank)."""
        journal = self.env['account.journal'].search([
            ('type', 'in', ['cash', 'bank']),
            ('company_id', '=', self.config_id.company_id.id),
        ], limit=1)

        return journal

    def cancel_payment(self, payment):
        """
        Cancel a payment.

        Args:
            payment (account.payment): Payment to cancel
        """
        self.ensure_one()

        if not payment:
            return

        try:
            if payment.state == 'posted':
                # Reset to draft
                payment.action_draft()

            if payment.state == 'draft':
                # Cancel the payment
                payment.action_cancel()

            _logger.info('Cancelled payment %s', payment.name)

            # Log success
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'sync',
                'direction': 'incoming',
                'endpoint': 'payment_cancellation',
                'status_code': 200,
                'payment_id': payment.id,
                'response_data': f'Payment {payment.name} cancelled',
            })

        except Exception as e:
            _logger.error('Failed to cancel payment %s: %s', payment.name, str(e))

            # Log error
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'error',
                'direction': 'incoming',
                'endpoint': 'payment_cancellation',
                'status_code': 0,
                'payment_id': payment.id,
                'error_message': str(e),
            })

            raise
