from odoo import models, fields, api


class SaleOrder(models.Model):
    """Extend sale.order to add Dotykačka order fields."""

    _inherit = 'sale.order'

    dotykacka_order_id = fields.Char(
        string='Dotykačka Order ID',
        help='Order ID from Dotykačka POS',
        copy=False,
        index=True,
        readonly=True,
    )

    dotykacka_receipt_number = fields.Char(
        string='Dotykačka Receipt Number',
        help='Receipt number from Dotykačka',
        readonly=True,
    )

    dotykacka_is_takeaway = fields.Boolean(
        string='Is Takeaway',
        default=False,
        help='Order is marked as takeaway in Dotykačka',
    )

    dotykacka_is_delivery = fields.Boolean(
        string='Is Delivery',
        default=False,
        help='Order is marked as delivery in Dotykačka',
    )

    dotykacka_sync_date = fields.Datetime(
        string='Dotykačka Last Sync',
        readonly=True,
        help='Last synchronization date from Dotykačka',
    )

    @api.model
    def _create_invoices(self, grouped=False, final=False, date=None):
        """Override to handle Dotykačka-specific invoice creation."""
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)

        # Copy Dotykačka fields to invoices
        for order in self:
            if order.dotykacka_order_id:
                order_invoices = moves.filtered(lambda m: m.invoice_line_ids.sale_line_ids.order_id == order)
                for invoice in order_invoices:
                    invoice.dotykacka_order_id = order.dotykacka_order_id
                    if order.dotykacka_receipt_number:
                        invoice.ref = order.dotykacka_receipt_number

        return moves
