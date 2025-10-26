"""Dotykačka Order Mapping."""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DotykackaOrderMapping(models.Model):
    """Track Dotykačka orders and their Odoo counterparts."""

    _name = 'dotykacka.order.mapping'
    _description = 'Dotykačka Order Mapping'
    _rec_name = 'dotykacka_receipt_id'
    _order = 'create_date desc'

    config_id = fields.Many2one(
        'dotykacka.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
        index=True
    )
    company_id = fields.Many2one(
        related='config_id.company_id',
        string='Company',
        store=True,
        readonly=True,
        index=True
    )

    # Dotykačka References
    dotykacka_receipt_id = fields.Char(
        string='Receipt ID',
        required=True,
        index=True,
        help='Dotykačka receipt/order ID'
    )
    dotykacka_order_number = fields.Char(
        string='Order Number',
        help='Dotykačka order number for display'
    )
    dotykacka_status = fields.Selection(
        [
            ('on_site', 'On Site'),
            ('takeaway', 'Takeaway'),
            ('delivery', 'Delivery'),
            ('other', 'Other'),
        ],
        string='Dotykačka Status',
        help='Order status in Dotykačka'
    )
    dotykacka_data = fields.Text(
        string='Dotykačka Data',
        help='Full order data from Dotykačka (JSON)'
    )

    # Odoo References
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        ondelete='restrict',
        index=True
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice',
        ondelete='restrict'
    )
    payment_ids = fields.Many2many(
        'account.payment',
        string='Payments',
        help='Payments linked to this order'
    )

    # Sync Status
    sync_status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('synced', 'Synced'),
            ('error', 'Error'),
            ('cancelled', 'Cancelled'),
            ('deleted', 'Deleted'),
        ],
        string='Sync Status',
        default='pending',
        required=True,
        index=True
    )
    sync_error = fields.Text(
        string='Sync Error',
        help='Error message if sync failed'
    )

    # Timestamps
    dotykacka_created_at = fields.Datetime(
        string='Created in Dotykačka',
        help='When order was created in Dotykačka'
    )
    dotykacka_updated_at = fields.Datetime(
        string='Updated in Dotykačka',
        help='When order was last updated in Dotykačka'
    )
    last_synced_at = fields.Datetime(
        string='Last Synced',
        help='When this order was last synced to Odoo'
    )

    # Flags
    needs_update = fields.Boolean(
        string='Needs Update',
        default=False,
        help='Set when Dotykačka order changed and needs resync'
    )
    deleted_in_dotykacka = fields.Boolean(
        string='Deleted in Dotykačka',
        default=False,
        help='Set when order was deleted in Dotykačka'
    )

    _sql_constraints = [
        ('dotykacka_receipt_config_uniq',
         'unique(dotykacka_receipt_id, config_id)',
         'Dotykačka receipt ID must be unique per configuration!'),
    ]

    def action_view_sale_order(self):
        """Open related sale order."""
        self.ensure_one()
        if not self.sale_order_id:
            raise ValidationError(_('No sale order linked to this mapping.'))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_invoice(self):
        """Open related invoice."""
        self.ensure_one()
        if not self.invoice_id:
            raise ValidationError(_('No invoice linked to this mapping.'))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_payments(self):
        """Open related payments."""
        self.ensure_one()
        if not self.payment_ids:
            raise ValidationError(_('No payments linked to this mapping.'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Payments'),
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.payment_ids.ids)],
        }

    def action_resync(self):
        """Manually trigger resync of this order."""
        self.ensure_one()

        # Mark for update
        self.write({
            'needs_update': True,
            'sync_status': 'pending',
        })

        # Trigger sync
        sync_service = self.env['dotykacka.sync.order']
        sync_service.sync_order(self.config_id, self.dotykacka_receipt_id)

    def action_cancel_order(self):
        """Cancel this order in Odoo (when deleted in Dotykačka)."""
        self.ensure_one()

        # Cancel sale order
        if self.sale_order_id and self.sale_order_id.state != 'cancel':
            self.sale_order_id.action_cancel()

        # Cancel invoice
        if self.invoice_id and self.invoice_id.state == 'posted':
            # Create reversal
            move_reversal = self.env['account.move.reversal'].with_context(
                active_model='account.move',
                active_ids=self.invoice_id.ids
            ).create({
                'date': fields.Date.today(),
                'reason': _('Order deleted in Dotykačka'),
                'journal_id': self.invoice_id.journal_id.id,
            })
            reversal = move_reversal.reverse_moves()

        # Cancel payments (if not reconciled)
        for payment in self.payment_ids:
            if payment.state != 'cancelled' and not payment.reconciled_bill_ids:
                payment.action_cancel()

        # Update mapping status
        self.write({
            'sync_status': 'cancelled',
            'deleted_in_dotykacka': True,
        })

    @api.model
    def find_or_create_mapping(self, config, dotykacka_receipt_id, dotykacka_data=None):
        """
        Find existing mapping or create new one.

        Args:
            config: dotykacka.config record
            dotykacka_receipt_id: Receipt ID from Dotykačka
            dotykacka_data: Optional dict with order data

        Returns:
            dotykacka.order.mapping: Mapping record
        """
        mapping = self.search([
            ('config_id', '=', config.id),
            ('dotykacka_receipt_id', '=', dotykacka_receipt_id),
        ], limit=1)

        if not mapping:
            vals = {
                'config_id': config.id,
                'dotykacka_receipt_id': dotykacka_receipt_id,
            }
            if dotykacka_data:
                import json
                vals['dotykacka_data'] = json.dumps(dotykacka_data)
                vals['dotykacka_status'] = dotykacka_data.get('status', 'other')
                vals['dotykacka_order_number'] = dotykacka_data.get('orderNumber')

            mapping = self.create(vals)

        return mapping

    @api.model
    def update_mapping(self, mapping, sale_order=None, invoice=None, payments=None):
        """
        Update mapping with Odoo references.

        Args:
            mapping: dotykacka.order.mapping record
            sale_order: sale.order record (optional)
            invoice: account.move record (optional)
            payments: account.payment recordset (optional)
        """
        vals = {
            'last_synced_at': fields.Datetime.now(),
            'sync_status': 'synced',
            'needs_update': False,
        }

        if sale_order:
            vals['sale_order_id'] = sale_order.id

        if invoice:
            vals['invoice_id'] = invoice.id

        if payments:
            vals['payment_ids'] = [(6, 0, payments.ids)]

        mapping.write(vals)

    @api.model
    def get_pending_syncs(self, config, limit=100):
        """
        Get orders that need to be synced.

        Args:
            config: dotykacka.config record
            limit: Maximum number of records to return

        Returns:
            dotykacka.order.mapping: Recordset of pending mappings
        """
        return self.search([
            ('config_id', '=', config.id),
            ('sync_status', '=', 'pending'),
            ('deleted_in_dotykacka', '=', False),
        ], limit=limit, order='create_date asc')

    @api.model
    def get_orders_needing_update(self, config, limit=100):
        """
        Get orders marked for update.

        Args:
            config: dotykacka.config record
            limit: Maximum number of records to return

        Returns:
            dotykacka.order.mapping: Recordset of mappings needing update
        """
        return self.search([
            ('config_id', '=', config.id),
            ('needs_update', '=', True),
            ('deleted_in_dotykacka', '=', False),
        ], limit=limit, order='dotykacka_updated_at desc')
