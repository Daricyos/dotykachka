"""Extend res.partner for Dotykačka integration."""

from odoo import fields, models


class ResPartner(models.Model):
    """Extend Partner to track Dotykačka customer ID."""

    _inherit = 'res.partner'

    dotykacka_customer_id = fields.Char(
        string='Dotykačka Customer ID',
        help='Customer ID from Dotykačka POS',
        copy=False,
        index=True
    )
    dotykacka_sync_date = fields.Datetime(
        string='Dotykačka Last Sync',
        help='When this customer was last synced from Dotykačka',
        readonly=True,
        copy=False
    )

    _sql_constraints = [
        ('dotykacka_customer_id_uniq',
         'unique(dotykacka_customer_id)',
         'Dotykačka Customer ID must be unique!'),
    ]
