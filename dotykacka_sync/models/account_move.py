"""Extend account.move for Dotykačka integration."""

from odoo import fields, models


class AccountMove(models.Model):
    """Extend Invoice to track Dotykačka invoice."""

    _inherit = 'account.move'

    dotykacka_receipt_id = fields.Char(
        string='Dotykačka Receipt ID',
        help='Receipt/Order ID from Dotykačka POS',
        copy=False,
        index=True
    )
    dotykacka_invoice_id = fields.Char(
        string='Dotykačka Invoice ID',
        help='Invoice ID from Dotykačka POS',
        copy=False
    )
    dotykacka_sync_date = fields.Datetime(
        string='Dotykačka Last Sync',
        help='When this invoice was last synced from Dotykačka',
        readonly=True,
        copy=False
    )
    dotykacka_config_id = fields.Many2one(
        'dotykacka.config',
        string='Dotykačka Configuration',
        help='Dotykačka configuration used for this invoice',
        ondelete='restrict',
        copy=False
    )
