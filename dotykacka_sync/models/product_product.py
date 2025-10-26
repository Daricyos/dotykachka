"""Extend product.product for Dotykačka integration."""

from odoo import fields, models


class ProductProduct(models.Model):
    """Extend Product to track Dotykačka product ID."""

    _inherit = 'product.product'

    dotykacka_product_id = fields.Char(
        string='Dotykačka Product ID',
        help='Product ID from Dotykačka POS',
        copy=False,
        index=True
    )
    dotykacka_sku = fields.Char(
        string='Dotykačka SKU',
        help='SKU from Dotykačka POS',
        copy=False
    )
    dotykacka_sync_date = fields.Datetime(
        string='Dotykačka Last Sync',
        help='When this product was last synced from Dotykačka',
        readonly=True,
        copy=False
    )

    _sql_constraints = [
        ('dotykacka_product_id_uniq',
         'unique(dotykacka_product_id)',
         'Dotykačka Product ID must be unique!'),
    ]
