from odoo import models, fields


class ResPartner(models.Model):
    """Extend res.partner to add Dotykačka customer fields."""

    _inherit = 'res.partner'

    dotykacka_customer_id = fields.Char(
        string='Dotykačka Customer ID',
        help='Customer ID from Dotykačka POS',
        copy=False,
        index=True,
    )

    dotykacka_display_name = fields.Char(
        string='Dotykačka Display Name',
        help='Display name from Dotykačka',
    )

    dotykacka_sync_date = fields.Datetime(
        string='Dotykačka Last Sync',
        readonly=True,
        help='Last synchronization date from Dotykačka',
    )
