"""Partner (Customer) extensions."""

from odoo import fields, models


class ResPartner(models.Model):
    """Extend res.partner with Dotykacka fields."""

    _inherit = 'res.partner'

    dotykacka_customer_id = fields.Char(
        string='Dotykacka Customer ID',
        readonly=True,
        copy=False,
        index=True,
        help='Customer ID from Dotykacka',
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
        """Check if partner is imported from Dotykacka."""
        for partner in self:
            partner.is_dotykacka_import = bool(partner.dotykacka_customer_id)

    def action_view_dotykacka_orders(self):
        """View orders from Dotykacka for this customer."""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Dotykacka Orders',
            'res_model': 'sale.order',
            'view_mode': 'tree,form',
            'domain': [
                ('partner_id', '=', self.id),
                ('is_dotykacka_import', '=', True),
            ],
        }
