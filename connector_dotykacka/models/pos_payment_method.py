"""Module for Dotykacka PoS Payment Method extension."""
__version__ = "1.1"

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PosPaymentMethod(models.Model):
    """Extension of pos.payment.method for dotykacka."""

    _inherit = 'pos.payment.method'

    def _get_payment_terminal_selection(self):
        """Add Dotykacka as Payment Terminal."""
        options = super(PosPaymentMethod, self)._get_payment_terminal_selection()
        return options + [('dotykacka', 'Dotykacka')]

    dotykacka_method_identifier = fields.Selection(
        [
            ('900000001', "Cash"),
            ('900000002', "Payment card"),
            ('900000003', "Check"),
            ('900000004', "Food/meal voucher"),
            ('900000009', "Bank transfer"),
            ('900000010', "Electronic food/meal voucher"),
            ('900000011', "Voucher"),
            ('901000001', "QERKO"),
            ('901000002', "Corrency"),
        ],
        "Payment Method",
        store=True,
    )

    @api.depends('is_cash_count')
    def _compute_hide_use_payment_terminal(self):
        """Allow payment terminals on Cash payment type."""
        no_terminals = not bool(self._fields['use_payment_terminal'].selection(self))
        for payment_method in self:
            payment_method.hide_use_payment_terminal = no_terminals
