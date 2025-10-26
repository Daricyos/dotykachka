"""Extend sale.order for Dotykačka integration."""

from odoo import fields, models


class SaleOrder(models.Model):
    """Extend Sale Order to track Dotykačka order/receipt."""

    _inherit = 'sale.order'

    dotykacka_receipt_id = fields.Char(
        string='Dotykačka Receipt ID',
        help='Receipt/Order ID from Dotykačka POS',
        copy=False,
        index=True
    )
    dotykacka_order_number = fields.Char(
        string='Dotykačka Order Number',
        help='Order number from Dotykačka POS',
        copy=False
    )
    dotykacka_status = fields.Selection(
        [
            ('on_site', 'On Site'),
            ('takeaway', 'Takeaway'),
            ('delivery', 'Delivery'),
            ('other', 'Other'),
        ],
        string='Dotykačka Status',
        help='Order status in Dotykačka POS',
        copy=False
    )
    dotykacka_sync_date = fields.Datetime(
        string='Dotykačka Last Sync',
        help='When this order was last synced from Dotykačka',
        readonly=True,
        copy=False
    )
    dotykacka_config_id = fields.Many2one(
        'dotykacka.config',
        string='Dotykačka Configuration',
        help='Dotykačka configuration used for this order',
        ondelete='restrict',
        copy=False
    )

    _sql_constraints = [
        ('dotykacka_receipt_id_uniq',
         'unique(dotykacka_receipt_id)',
         'Dotykačka Receipt ID must be unique!'),
    ]
