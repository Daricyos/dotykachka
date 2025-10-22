"""Module for Dotykacka Product object extension."""
__version__ = "1.0"

from odoo import fields, models


class ProductProduct(models.Model):
    """Extension of Product Variant model."""

    _inherit = "product.product"

    dotykacka_id = fields.Char(  # Using Char, as dotykacka API returns bigger int as odoo uses
        "Dotykacka ID", company_dependent=True, check_company=True
    )
    dotykacka_exported = fields.Boolean(company_dependent=True, check_company=True)
    dotykacka_last_update = fields.Datetime(
        tracking=True,
        company_dependent=True,
        check_company=True,
        help="Date and Time at which the product was last updated in dotykacka.",
    )
    dotykacka_created_at = fields.Datetime(
        "Dotykacka Create Time", tracking=True, company_dependent=True, check_company=True
    )
    dotykacka_sync_disabled = fields.Boolean(
        "Disabled Dotykacka Synchronization",
        default=False,
        tracking=True,
    )

    def write(self, values):
        """
        Override :class:`ProductProduct` :func:`write`.

        Custom processes for Dotykacka:
        """
        if not self.env.context.get('dotykacka_noupdate'):
            values['dotykacka_exported'] = False
        res = super(ProductProduct, self).write(values)
        return res


class ProductCategory(models.Model):
    """Extending product.category class by adding dotykacka related fields."""

    _inherit = 'product.category'

    dotykacka_category_id = fields.Char(
        "Dotykacka Category ID", company_dependent=True, check_company=True
    )
