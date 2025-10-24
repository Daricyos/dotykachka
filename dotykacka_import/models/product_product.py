"""Product extensions."""

from odoo import fields, models


class ProductProduct(models.Model):
    """Extend product.product with Dotykacka fields."""

    _inherit = 'product.product'

    dotykacka_product_id = fields.Char(
        string='Dotykacka Product ID',
        readonly=True,
        copy=False,
        index=True,
        help='Product ID from Dotykacka',
    )
    dotykacka_config_id = fields.Many2one(
        'dotykacka.config',
        string='Dotykacka Configuration',
        readonly=True,
        copy=False,
        ondelete='restrict',
    )
    is_dotykacka_import = fields.Boolean(
        string='Imported from Dotykacka',
        compute='_compute_is_dotykacka_import',
        store=True,
    )

    def _compute_is_dotykacka_import(self):
        """Check if product is imported from Dotykacka."""
        for product in self:
            product.is_dotykacka_import = bool(product.dotykacka_product_id)
