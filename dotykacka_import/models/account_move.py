"""Account Move (Invoice) extensions."""

from odoo import fields, models


class AccountMove(models.Model):
    """Extend account.move with Dotykacka fields."""

    _inherit = 'account.move'

    dotykacka_order_id = fields.Char(
        string='Dotykacka Order ID',
        related='invoice_origin_id.dotykacka_order_id',
        store=True,
        readonly=True,
        help='Related Dotykacka order ID',
    )
    dotykacka_config_id = fields.Many2one(
        'dotykacka.config',
        string='Dotykacka Configuration',
        compute='_compute_dotykacka_fields',
        store=True,
        readonly=True,
    )
    is_dotykacka_import = fields.Boolean(
        string='From Dotykacka',
        compute='_compute_dotykacka_fields',
        store=True,
    )

    invoice_origin_id = fields.Many2one(
        'sale.order',
        compute='_compute_invoice_origin',
        store=True,
    )

    def _compute_invoice_origin(self):
        """Compute related sale order."""
        for move in self:
            if move.move_type in ['out_invoice', 'out_refund'] and move.invoice_origin:
                sale_order = self.env['sale.order'].search([
                    ('name', '=', move.invoice_origin)
                ], limit=1)
                move.invoice_origin_id = sale_order.id
            else:
                move.invoice_origin_id = False

    def _compute_dotykacka_fields(self):
        """Compute Dotykacka related fields."""
        for move in self:
            if move.invoice_origin_id:
                move.dotykacka_config_id = move.invoice_origin_id.dotykacka_config_id.id
                move.is_dotykacka_import = bool(move.invoice_origin_id.dotykacka_order_id)
            else:
                move.dotykacka_config_id = False
                move.is_dotykacka_import = False
