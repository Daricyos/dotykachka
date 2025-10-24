from odoo import models, fields


class AccountPayment(models.Model):
    """Extend account.payment to add Dotykačka payment fields."""

    _inherit = 'account.payment'

    dotykacka_order_id = fields.Char(
        string='Dotykačka Order ID',
        help='Related Dotykačka order ID',
        copy=False,
        index=True,
        readonly=True,
    )

    dotykacka_payment_method_id = fields.Char(
        string='Dotykačka Payment Method ID',
        help='Payment method ID from Dotykačka',
        readonly=True,
    )

    dotykacka_payment_method_name = fields.Char(
        string='Dotykačka Payment Method',
        help='Payment method name from Dotykačka',
        readonly=True,
    )

    dotykacka_sync_date = fields.Datetime(
        string='Dotykačka Last Sync',
        readonly=True,
        help='Last synchronization date from Dotykačka',
    )
