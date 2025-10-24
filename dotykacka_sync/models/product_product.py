from odoo import models, fields


class ProductProduct(models.Model):
    """Extend product.product to add Dotykačka product fields."""

    _inherit = 'product.product'

    dotykacka_product_id = fields.Char(
        string='Dotykačka Product ID',
        help='Product ID from Dotykačka POS',
        copy=False,
        index=True,
    )

    dotykacka_display = fields.Char(
        string='Dotykačka Display',
        help='Display setting from Dotykačka',
    )

    dotykacka_sync_date = fields.Datetime(
        string='Dotykačka Last Sync',
        readonly=True,
        help='Last synchronization date from Dotykačka',
    )
