"""Dotykacka Webhook Controllers."""

import logging
from odoo import http, SUPERUSER_ID
from odoo.http import request

_logger = logging.getLogger(__name__)


class DotykackaWebhookController(http.Controller):
    """Handle webhooks from Dotykacka."""

    @http.route(
        '/dotykacka/webhook/<int:config_id>',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def receive_webhook(self, config_id, **kwargs):
        """
        Receive webhook from Dotykacka.

        :param config_id: ID of dotykacka.config
        :return: dict with status
        """
        try:
            data = request.jsonrequest

            _logger.info(f"Webhook received for config {config_id}: {data}")

            # Get configuration
            config = request.env['dotykacka.config'].sudo().browse(config_id)

            if not config.exists() or not config.active:
                _logger.warning(f"Invalid or inactive config: {config_id}")
                return {'status': 'error', 'message': 'Invalid configuration'}

            # Extract event information
            event_type = data.get('event')  # e.g., 'order.created', 'order.updated', 'order.deleted'
            event_data = data.get('data', {})

            _logger.info(f"Processing event: {event_type}")

            # Update webhook trigger count
            webhook = request.env['dotykacka.webhook'].sudo().search([
                ('config_id', '=', config_id),
                ('event_type', '=', 'order'),
            ], limit=1)

            if webhook:
                webhook.increment_trigger_count()

            # Process event based on type
            if event_type == 'order.created':
                return self._handle_order_created(config, event_data)
            elif event_type == 'order.updated':
                return self._handle_order_updated(config, event_data)
            elif event_type == 'order.deleted':
                return self._handle_order_deleted(config, event_data)
            elif event_type == 'customer.created' or event_type == 'customer.updated':
                return self._handle_customer_event(config, event_data)
            else:
                _logger.warning(f"Unhandled event type: {event_type}")
                return {'status': 'ignored', 'message': f'Event type {event_type} not handled'}

        except Exception as e:
            _logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

    def _handle_order_created(self, config, order_data):
        """
        Handle order.created event.

        :param config: dotykacka.config record
        :param order_data: dict with order data
        :return: dict with status
        """
        try:
            importer = request.env['dotykacka.importer'].sudo()
            importer._process_order(config, order_data)

            return {'status': 'success', 'message': 'Order created'}

        except Exception as e:
            _logger.error(f"Error handling order.created: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    def _handle_order_updated(self, config, order_data):
        """
        Handle order.updated event.

        :param config: dotykacka.config record
        :param order_data: dict with order data
        :return: dict with status
        """
        try:
            order_id = order_data.get('id')

            # Find existing order
            sale_order = request.env['sale.order'].sudo().search([
                ('dotykacka_order_id', '=', order_id),
                ('dotykacka_config_id', '=', config.id),
            ], limit=1)

            if not sale_order:
                # Order doesn't exist yet, create it
                _logger.info(f"Order {order_id} not found, creating new order")
                importer = request.env['dotykacka.importer'].sudo()
                importer._process_order(config, order_data)
                return {'status': 'success', 'message': 'Order created'}

            # Update existing order
            importer = request.env['dotykacka.importer'].sudo()
            importer._update_order(config, sale_order, order_data)

            return {'status': 'success', 'message': 'Order updated'}

        except Exception as e:
            _logger.error(f"Error handling order.updated: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    def _handle_order_deleted(self, config, order_data):
        """
        Handle order.deleted event.

        :param config: dotykacka.config record
        :param order_data: dict with order data
        :return: dict with status
        """
        try:
            order_id = order_data.get('id')

            importer = request.env['dotykacka.importer'].sudo()
            importer.cancel_order(config, order_id)

            return {'status': 'success', 'message': 'Order cancelled'}

        except Exception as e:
            _logger.error(f"Error handling order.deleted: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    def _handle_customer_event(self, config, customer_data):
        """
        Handle customer events.

        :param config: dotykacka.config record
        :param customer_data: dict with customer data
        :return: dict with status
        """
        try:
            importer = request.env['dotykacka.importer'].sudo()
            importer._import_customer(config, customer_data)

            return {'status': 'success', 'message': 'Customer processed'}

        except Exception as e:
            _logger.error(f"Error handling customer event: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    @http.route(
        '/dotykacka/webhook/test',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def test_webhook(self, **kwargs):
        """Test webhook endpoint."""
        _logger.info("Test webhook received")
        return {'status': 'success', 'message': 'Webhook is working!'}
