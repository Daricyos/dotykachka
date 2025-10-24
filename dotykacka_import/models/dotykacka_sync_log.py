"""Dotykacka Sync Log."""

import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)


class DotykackaSyncLog(models.Model):
    """Log synchronization operations."""

    _name = 'dotykacka.sync.log'
    _description = 'Dotykacka Sync Log'
    _order = 'create_date desc'
    _rec_name = 'entity_id'

    config_id = fields.Many2one(
        'dotykacka.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
        index=True,
    )
    entity_type = fields.Selection(
        [
            ('order', 'Order'),
            ('customer', 'Customer'),
            ('product', 'Product'),
            ('payment', 'Payment'),
        ],
        string='Entity Type',
        required=True,
        index=True,
    )
    entity_id = fields.Char(
        string='Entity ID',
        required=True,
        help='Dotykacka entity ID',
        index=True,
    )
    status = fields.Selection(
        [
            ('created', 'Created'),
            ('updated', 'Updated'),
            ('skipped', 'Skipped'),
            ('cancelled', 'Cancelled'),
            ('error', 'Error'),
        ],
        string='Status',
        required=True,
        index=True,
    )
    message = fields.Text(string='Message')
    create_date = fields.Datetime(
        string='Date',
        readonly=True,
        index=True,
    )

    def action_view_related(self):
        """Open related Odoo record."""
        self.ensure_one()

        if self.entity_type == 'order':
            order = self.env['sale.order'].search([
                ('dotykacka_order_id', '=', self.entity_id),
                ('dotykacka_config_id', '=', self.config_id.id),
            ], limit=1)

            if order:
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'sale.order',
                    'view_mode': 'form',
                    'res_id': order.id,
                }

        elif self.entity_type == 'customer':
            partner = self.env['res.partner'].search([
                ('dotykacka_customer_id', '=', self.entity_id),
                ('dotykacka_config_id', '=', self.config_id.id),
            ], limit=1)

            if partner:
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'res.partner',
                    'view_mode': 'form',
                    'res_id': partner.id,
                }

        elif self.entity_type == 'product':
            product = self.env['product.product'].search([
                ('dotykacka_product_id', '=', self.entity_id),
                ('dotykacka_config_id', '=', self.config_id.id),
            ], limit=1)

            if product:
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'product.product',
                    'view_mode': 'form',
                    'res_id': product.id,
                }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Not Found',
                'message': 'Related record not found in Odoo.',
                'type': 'warning',
            }
        }
