"""Module for Dotykacka endpoints."""

from odoo import http, SUPERUSER_ID

DEFAULT_ERROR_VALUE = -1


class DotykackaEndpoint(http.Controller):
    """Endpoints for requests from Dotykacka."""

    @http.route(
        '/rest/v1/dotykacka/order/map',
        type='json',
        auth="public",
        methods=['POST'],
        csrf=False,  # 3rd party wouldn't work -> authenticate method
    )
    def create_dotykacka_order(self):
        """Endpoint for mapping dotykacka data to existing dotykacka orders."""
        parser = self._prepare_parser('rest/v1/dotykacka/order/map')
        order_data = parser.data.get('order', None)
        parser.order_map(order_data)
        parser.clear()
        return True

    @http.route(
        '/rest/v1/dotykacka/order/update',
        type='json',
        auth="public",
        methods=['POST'],
        csrf=False,  # 3rd party wouldn't work -> authenticate method
    )
    def update_dotykacka_order(self):
        """Endpoint for updating dotykacka order with new information."""
        parser = self._prepare_parser('rest/v1/dotykacka/order/update')
        for order in parser.data.get('items', []):
            parser.order_update(order)
            parser.env.cr.commit()  # pylint:disable=E8102
        parser.clear()
        return True

    @staticmethod
    def _prepare_parser(endpoint_path: str):
        parser = http.request.env['dotykacka.parser'].with_user(SUPERUSER_ID).sudo()
        parser.prepare(http.request)
        parser.log_request(endpoint_path)
        return parser
