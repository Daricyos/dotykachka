"""Sale Order extensions."""

from odoo import fields, models


class SaleOrder(models.Model):
    """Extend sale.order with Dotykacka fields."""

    _inherit = 'sale.order'

    dotykacka_order_id = fields.Char(
        string='Dotykacka Order ID',
        readonly=True,
        copy=False,
        index=True,
        help='Order ID from Dotykacka POS',
    )
    dotykacka_config_id = fields.Many2one(
        'dotykacka.config',
        string='Dotykacka Configuration',
        readonly=True,
        copy=False,
        ondelete='restrict',
    )
    dotykacka_receipt_number = fields.Char(
        string='Receipt Number',
        readonly=True,
        copy=False,
        help='Receipt number from Dotykacka',
    )
    dotykacka_created_at = fields.Datetime(
        string='Dotykacka Created At',
        readonly=True,
        copy=False,
        help='Date and time when order was created in Dotykacka',
    )
    is_dotykacka_import = fields.Boolean(
        string='Imported from Dotykacka',
        compute='_compute_is_dotykacka_import',
        store=True,
    )

    def _compute_is_dotykacka_import(self):
        """Check if order is imported from Dotykacka."""
        for order in self:
            order.is_dotykacka_import = bool(order.dotykacka_order_id)

    def action_view_dotykacka_config(self):
        """Open Dotykacka configuration."""
        self.ensure_one()
        if not self.dotykacka_config_id:
            return

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dotykacka.config',
            'view_mode': 'form',
            'res_id': self.dotykacka_config_id.id,
            'target': 'new',
        }

    def action_view_sync_logs(self):
        """View sync logs for this order."""
        self.ensure_one()
        if not self.dotykacka_order_id:
            return

        return {
            'type': 'ir.actions.act_window',
            'name': 'Sync Logs',
            'res_model': 'dotykacka.sync.log',
            'view_mode': 'tree,form',
            'domain': [
                ('entity_type', '=', 'order'),
                ('entity_id', '=', self.dotykacka_order_id),
            ],
            'context': {'create': False},
        }
