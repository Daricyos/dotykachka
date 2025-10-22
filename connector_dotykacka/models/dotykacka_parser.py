"""Module for logging Dotykacka PoS orders."""
__version__ = "1.0"

import json
import logging
from datetime import datetime

from odoo import fields, http, models, SUPERUSER_ID

LOG_ORIGIN = __name__
DEFAULT_ERROR_VALUE = -1

_logger = logging.getLogger(LOG_ORIGIN)


class DotykackaParser(models.TransientModel):
    """Parser for dotykacka data."""

    _name = 'dotykacka.parser'

    data = None

    # pylint:disable=W0201
    def prepare(self, request: http.request):
        """
        Initialize processor.

        :param request: Request object
        """
        self.request = request
        self.data = request.jsonrequest

    def order_map(self, order) -> bool:
        """
        Map dotykacka.order created in odoo to incoming dotykacka data.

        :return: True if successfully mapped else False
        """
        if not order:
            return False
        external_id = order.get('external-id', DEFAULT_ERROR_VALUE)
        dotykacka_order = (
            self.env['dotykacka.order']
            .with_user(SUPERUSER_ID)
            .sudo()
            .search([('reference', '=', external_id)])
        )
        if not dotykacka_order:
            _logger.error('Error dotykacka/order/create: %s', self.data)
            return False
        data = {
            'state': 'sent',
            'dotykacka_id': order.get('id', DEFAULT_ERROR_VALUE),
            'order_series_id': order.get('order-series-id', DEFAULT_ERROR_VALUE),
            'price_total': order.get('price-total', DEFAULT_ERROR_VALUE),
            'updated_at': fields.Datetime.now(),
        }
        dotykacka_order.update(data)
        self._check_queue(dotykacka_order, order)

        return True

    def order_create(self, order):
        """
        Create new dotykacka.order and related pos order.

        :return: dotykacka.order if successfully created else False
        """
        rel_order_id = order.get('relatedorderid', DEFAULT_ERROR_VALUE)
        if not rel_order_id:
            # Skip orders that are not in odoo and doesn't have external id.
            return False

        rel_dotykacka_order, rel_order = self.order_refund(order)
        if not (rel_dotykacka_order or rel_order):
            return False

        if rel_dotykacka_order.model == 'pos.order':
            reference = rel_order.pos_reference
        else:
            reference = rel_order.barcode

        dotykacka_order = rel_dotykacka_order.copy(
            {
                'state': self.get_state(order),
                'record_id': rel_order.id,
                'reference': reference,
                'dotykacka_id': order.get('orderid', DEFAULT_ERROR_VALUE),
                'order_series_id': order.get('orderseriesid', DEFAULT_ERROR_VALUE),
                'note': order.get('note', False),
                'created_at': fields.Datetime.now(),
            }
        )
        rel_order.write({'dotykacka_order_id': dotykacka_order.id})
        return dotykacka_order

    def order_update(self, order) -> bool:
        """
        Update dotykacka.order created in odoo with incoming dotykacka data.

        :return: True if successfully updated else False
        """
        order_id = order.get('orderid', DEFAULT_ERROR_VALUE)
        related_order_id = order.get('relatedorderid', DEFAULT_ERROR_VALUE)
        dotykacka_order = self.env['dotykacka.order'].search(
            ['|', ('dotykacka_id', '=', order_id), ('dotykacka_id', '=', related_order_id)]
        )
        orders_count = len(dotykacka_order)
        if orders_count == 1 and dotykacka_order.dotykacka_id == str(order_id):
            # Only one matching Order exists in odoo
            return self._update_order(dotykacka_order, order)

        if orders_count == 1 and dotykacka_order.dotykacka_id != str(order_id) and related_order_id:
            # Related Order exists in odoo but refund wasn't created yet.
            dotykacka_order = self.order_create(order)
            self.env.cr.commit()  # pylint:disable=E8102
            return self._update_order(dotykacka_order, order)

        if orders_count > 1:
            # Matching Order and related refunds exists in odoo.
            filter_by = str(order_id) if not related_order_id else str(related_order_id)
            dotykacka_order = dotykacka_order.filtered(lambda o: o.dotykacka_id == filter_by)
            return self._update_order(dotykacka_order, order)
        # No matching DOrder or related refunds exists in odoo.
        external_id = order.get('externalid', DEFAULT_ERROR_VALUE)
        return self._queue_order(order, 'order_external_id', external_id)

    def order_refund(self, order):
        """Create refund order or queue data."""
        rel_order_id = order.get('relatedorderid', DEFAULT_ERROR_VALUE)
        rel_dotykacka_order = self.env['dotykacka.order'].search(
            [('dotykacka_id', '=', rel_order_id)]
        )
        if not rel_dotykacka_order:
            self._queue_order(order, 'order_related_id', rel_order_id)
            return rel_dotykacka_order, False

        rel_order = self.env[rel_dotykacka_order.model].browse(rel_dotykacka_order.record_id)
        new_order = rel_order.refund_dotykacka()
        if not new_order:
            self._queue_order(order, 'order_related_id', rel_order_id)
        return rel_dotykacka_order, new_order

    def get_state(self, data):
        """Get dotykacka.order state based on incoming data."""
        dk_env = self.env['dotykacka.order']
        flags = data.get('flags', 0)
        state = 'created'
        if not flags:
            state = 'new'
        elif dk_env.is_flag_set(flags, flag=13):  # FISCALIZATION_FAILED
            state = 'error'
        elif dk_env.any_flag_set(flags, [0, 1]):
            state = 'canceled'
        elif data.get('printed', 0):
            state = 'printed'
        return state

    def _update_order(self, dotykacka_order, order) -> bool:
        state = self.get_state(order)
        dotykacka_order.write(
            {
                'state': state,
                'note': order.get('note', False),
                'updated_at': fields.Datetime.now(),
            }
        )
        return True

    def _queue_order(self, order, related_field, field_value) -> bool:
        return self.env['dotykacka.queue'].create(
            {
                related_field: field_value,
                'request_data': json.dumps(order),
            }
        )

    def _check_queue(self, dotykacka_order, data):
        """
        Map matching data in queue to related dotykacka.order.

        :param dotykacka_order: Record Dotykacka Order
        :param data: Prepared data for dotykacka order
        """
        external_id = data.get('external-id', DEFAULT_ERROR_VALUE)
        self._process_queue(dotykacka_order, 'order_external_id', external_id)
        self._process_queue(dotykacka_order, 'order_related_id', dotykacka_order.dotykacka_id)

    def _process_queue(self, dotykacka_order, field, value):
        """
        Process requests in queue based on searched values.

        After successfully processing data in queue, delete the record.

        :param dotykacka_order: Record Dotykacka Order
        :param field: Searched key
        :param value: searched value
        """
        queue_records = self.env['dotykacka.queue'].search([(field, '=', value)])
        for queue_record in queue_records:
            order_data = json.loads(queue_record.request_data)
            if field == 'order_external_id':
                self._update_order(dotykacka_order, order_data)
            elif field == 'order_related_id':
                self.order_create(order_data)
            queue_record.unlink()

    def log_request(self, endpoint):
        """Log request to api logger."""
        self.env['api_manager.logger'].create(
            {
                'created_at': datetime.now(),
                'origin': LOG_ORIGIN,
                'direction': "incoming",
                'data': {
                    "endpoint": endpoint,
                    "headers": self.request.httprequest.headers,
                    "cookies": self.request.httprequest.cookies,
                    "data": self.request.httprequest.data,
                },
            }
        )

    def clear(self):
        """Clear object and flush any temporary data."""
        self.data = False
        self.env.flush_all()
