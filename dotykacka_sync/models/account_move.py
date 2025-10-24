from odoo import models, fields


class AccountMove(models.Model):
    """Extend account.move to add Dotykačka invoice fields."""

    _inherit = 'account.move'

    dotykacka_order_id = fields.Char(
        string='Dotykačka Order ID',
        help='Related Dotykačka order ID',
        copy=False,
        index=True,
        readonly=True,
    )

    dotykacka_sync_date = fields.Datetime(
        string='Dotykačka Last Sync',
        readonly=True,
        help='Last synchronization date from Dotykačka',
    )
