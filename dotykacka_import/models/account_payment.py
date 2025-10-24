"""Account Payment extensions."""

from odoo import fields, models


class AccountPayment(models.Model):
    """Extend account.payment with Dotykacka fields."""

    _inherit = 'account.payment'

    dotykacka_payment_method = fields.Selection(
        [
            ('CASH', 'Cash'),
            ('CARD', 'Payment Card'),
            ('CHECK', 'Check'),
            ('VOUCHER', 'Food/Meal Voucher'),
            ('BANK_TRANSFER', 'Bank Transfer'),
            ('ELECTRONIC_VOUCHER', 'Electronic Food/Meal Voucher'),
            ('COUPON', 'Voucher/Coupon'),
            ('QERKO', 'QERKO'),
            ('CORRENCY', 'Currency'),
            ('GLOVO', 'Glovo'),
            ('WOLT', 'Wolt'),
            ('BOLT', 'Bolt Food'),
            ('UBER_EATS', 'Uber Eats'),
        ],
        string='Dotykacka Payment Method',
        readonly=True,
        help='Payment method from Dotykacka POS',
    )
    is_dotykacka_import = fields.Boolean(
        string='From Dotykacka',
        compute='_compute_is_dotykacka_import',
        store=True,
    )

    def _compute_is_dotykacka_import(self):
        """Check if payment is from Dotykacka."""
        for payment in self:
            payment.is_dotykacka_import = bool(payment.dotykacka_payment_method)
