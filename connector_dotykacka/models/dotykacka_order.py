"""Module for logging Dotykacka PoS orders."""
__version__ = "1.0"

import logging
import re
import time
from typing import List

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class DotykackaOrder(models.Model):
    """Dotykacka order representation."""

    _name = 'dotykacka.order'
    _order = 'write_date desc'
    _inherit = ['mail.thread']

    name = fields.Char(compute='_compute_name', store=True, readonly=True)
    cloud_id = fields.Char("Cloud ID", readonly=True, required=True, copy=True)
    branch_id = fields.Char("Branch ID", readonly=True, required=True, copy=True)
    model_id = fields.Many2one(
        comodel_name='ir.model',
        string="Model",
        index=True,
        required=True,
        readonly=True,
        domain=[('name', 'like', '%order%')],
        copy=True,
        ondelete='cascade',
    )
    model = fields.Char(related='model_id.model', readonly=True, copy=True)
    model_name = fields.Char(related='model_id.name', readonly=True, copy=True)
    record_id = fields.Integer(string="Order ID", readonly=True, required=True, copy=False)
    record_name = fields.Char(
        string="Order Name", compute='_compute_record_name', store=True, readonly=True, copy=False
    )
    company_id = fields.Many2one(
        'res.company', string="Company", readonly=True, required=True, copy=True
    )
    reference = fields.Char(index=True, copy=False)
    dotykacka_id = fields.Char("Dotykacka ID", copy=False)
    order_series_id = fields.Char("Receipt No.", copy=False)
    updated_at = fields.Datetime(readonly=True, tracking=True, copy=False)
    created_at = fields.Datetime(readonly=True, tracking=True, copy=False)
    state = fields.Selection(
        [
            ('new', 'New'),
            ('sent', 'Sent'),
            ('created', 'Created'),
            ('printed', 'Printed'),
            ('canceled', 'Canceled'),
            ('error', 'Errored'),
        ],
        default='new',
        tracking=True,
        copy=False,
    )
    note = fields.Char()
    price_total = fields.Float("Dotykacka Price Total", copy=False)

    _sql_constraints = [
        (
            'external_id_uniq',
            'unique(dotykacka_id)',
            """Dotykacka Order must refer to unique id!""",
        ),
    ]

    @api.depends('model', 'record_id')
    def _compute_record_name(self):
        """Compute related record name."""
        for rec in self:
            rec.record_name = rec.env[rec.model].browse(rec.record_id).name

    @api.depends('model_name', 'record_name')
    def _compute_name(self):
        """Compute related record name."""
        for rec in self:
            rec.name = f"{rec.model_name}/{rec.record_name}"

    # pylint:disable=W8106,W8102,R0201
    # see https://github.com/OCA/pylint-odoo/issues/257
    def unlink(self):
        """Prevent record deletion."""
        raise UserError(_('Dotykacka Order record cannot be manually deleted.'))

    # pylint:disable=W8106
    def write(self, vals):
        """Validate status changes."""
        error_msg = """Dotykacka Order cannot be changed back to previous state!
        Order: %s
        Change: %s -> %s"""
        valid_previous_states = {
            'canceled': ['new', 'sent', 'created', 'printed', 'canceled'],
            'error': ['new', 'sent', 'created', 'printed', 'canceled', 'error'],
            'new': ['new'],
            'sent': ['new', 'sent'],
            'created': ['new', 'sent', 'created'],
            'printed': ['new', 'sent', 'created', 'printed'],
        }
        for order in self:
            state = vals.get('state', False)
            if not state:
                continue
            related_order = self.env[order.model].browse(order.record_id)

            if state == 'sent' and not related_order.sent_to_terminal:
                related_order.update({'sent_to_terminal': True})
            elif state == 'printed' and not related_order.printed:
                related_order.update({'sent_to_terminal': True, 'printed': True})

            if order.state not in valid_previous_states[state]:
                _logger.warning(error_msg, order.name, order.state.capitalize(), state.capitalize())
                vals['state'] = order.state

            note = vals.get('note', False)
            if note:
                data = order.get_dotykacka_refund(related_order)
                order.process_dotykacka_refund(related_order, data)

        return super(DotykackaOrder, self).write(vals)

    @staticmethod
    def _filter_dotykacka_lines(order_items, line) -> iter:
        """
        Filter dotykacka order items by product and discount.

        :param order_items: order items from dotykacka
        :param line: line from pos.order

        :return: iterator of filtered items
        """
        product_id = line.product_id.dotykacka_id
        discount = int(line.discount)
        return filter(
            lambda item: (
                item['_productId'] == product_id and int(item['discountPercent']) == discount
            ),
            order_items,
        )

    def get_dotykacka_refund(self, related_order):
        """
        Get data and check if return should be created.

        :param related_order: Related pos order record.
        """
        request = self.env.ref('connector_dotykacka.api_request_dotykacka_get_orders')
        time.sleep(10)
        data = request.send_request_dotykacka(
            params={
                "{cloud_id}": self.cloud_id,
            },
            args={
                'include': 'orderItems,moneyLogs',
                'filter': f'id%7Ceq%7C{self.dotykacka_id}',  # | is encoded to %7C
            },
            return_type='decoded',
        )
        if not data:
            err_msg = f"No data from dotykacka returned!\nOrder: {related_order.name}"
            raise ValidationError(_(err_msg))
        orders = data.get('data', [])
        if len(orders) > 1:
            err_msg = (
                "Request to get dotykacka order returned multiple results!"
                f"\nOrder: {related_order.name}"
            )
            raise ValidationError(_(err_msg))
        if len(orders) < 0:
            err_msg = (
                "Request to get dotykacka order didn't return any results!"
                f"\nOrder: {related_order.name}"
            )
            raise ValidationError(_(err_msg))
        return orders[0]

    def process_dotykacka_refund(self, related_order, order) -> bool:
        """
        Create order return and confirm it.

        :param order: Data from dotykacka
        :param related_order: Related pos order record.

        :return: True if refund was created, False otherwise.
        """
        order_items = order.get('orderItems', False)
        payment_type = order.get('moneyLogs', False)
        if not payment_type or len(payment_type) <= 0 or not order_items or len(order_items) <= 0:
            return False
        payment_type = payment_type[0]
        if self.model == 'pos.order':
            # pylint:disable=W0212
            self.__class__._validate_retail_refund(related_order, order_items)
            related_order.add_dotykacka_payment(payment_type.get('paymentTypeId', False))
            related_order.action_pos_order_paid()
        return True

    # pylint: disable=W0640
    @classmethod
    def _validate_retail_refund(cls, related_order, order_items):
        """
        Match pos.order lines to dotykacka order lines.

        :param related_order: pos.order record
        :param order_items: order items from dotykacka
        """
        currency = related_order.pricelist_id.currency_id
        for line in related_order.lines:
            filtered_data = list(cls._filter_dotykacka_lines(order_items, line))

            results = {}
            for key, result_type in {
                'quantity': int,
                'totalPriceWithoutVat': float,
                'totalPriceWithVat': float,
            }.items():
                values = [item.get(key, 0) for item in filtered_data]
                result = sum(map(result_type, values))
                if result_type == float:
                    result = currency.round(result)
                results[key] = result

            if not results['quantity']:
                line.unlink()
                continue

            line.qty = results['quantity']
            line.price_subtotal = results['totalPriceWithoutVat']
            line.price_subtotal_incl = results['totalPriceWithVat']
        related_order._compute_amount()  # pylint:disable=W0212

    @staticmethod
    def _is_in_flag_list(flags: int, flag_list: List[int]):
        """Check if flags are in flag list."""
        return ((flags & (1 << flag)) != 0 for flag in flag_list)

    def any_flag_set(self, flags: int, flag_list: List[int]) -> bool:
        """
        Check if flag is set.

        :param flags: int representing flags (Binary representation)
        :param flag_list: List of flags to check
            See: https://docs.api.dotypos.com/entity/order#order-flags
        """
        return any(self._is_in_flag_list(flags, flag_list))

    def all_flag_set(self, flags: int, flag_list: List[int]) -> bool:
        """
        Check if flag is set.

        :param flags: int representing flags (Binary representation)
        :param flag_list: List of flags to check
            See: https://docs.api.dotypos.com/entity/order#order-flags
        """
        return all(self._is_in_flag_list(flags, flag_list))

    def is_flag_set(self, flags: int, flag: int) -> bool:
        """
        Check if flag is set.

        :param flags: int representing flags (Binary representation)
        :param flag: Integer representing FLaG
            See: https://docs.api.dotypos.com/entity/order#order-flags
        """
        return all(self._is_in_flag_list(flags, [flag]))
