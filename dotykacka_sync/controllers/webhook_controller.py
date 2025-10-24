import json
import logging
import hmac
import hashlib
from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class DotykackaWebhookController(http.Controller):
    """Controller for receiving webhooks from Dotykačka."""

    @http.route(
        '/dotykacka/webhook/<int:config_id>',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def webhook_receiver(self, config_id, **kwargs):
        """
        Receive and process webhooks from Dotykačka.

        URL format: /dotykacka/webhook/{config_id}

        Args:
            config_id (int): Dotykačka configuration ID

        Returns:
            dict: Response with status
        """
        try:
            # Get the configuration
            config = request.env['dotykacka.config'].sudo().browse(config_id)
            if not config.exists():
                _logger.error('Configuration %s not found', config_id)
                return {'status': 'error', 'message': 'Configuration not found'}

            if not config.active or config.status != 'active':
                _logger.warning('Configuration %s is not active', config_id)
                return {'status': 'error', 'message': 'Configuration not active'}

            # Get webhook data
            webhook_data = request.jsonrequest
            if not webhook_data:
                _logger.error('Empty webhook data received')
                return {'status': 'error', 'message': 'Empty webhook data'}

            # Validate webhook signature if secret is configured
            if config.webhook_secret:
                if not self._validate_signature(request, config.webhook_secret):
                    _logger.error('Invalid webhook signature')
                    return {'status': 'error', 'message': 'Invalid signature'}

            # Log incoming webhook
            request.env['dotykacka.sync.log'].sudo().create({
                'config_id': config_id,
                'log_type': 'webhook',
                'direction': 'incoming',
                'endpoint': '/dotykacka/webhook',
                'status_code': 200,
                'request_data': json.dumps(webhook_data),
            })

            # Process webhook based on event type
            event_type = webhook_data.get('event')
            event_data = webhook_data.get('data', {})

            _logger.info('Received webhook: %s for config %s', event_type, config_id)

            if event_type == 'order.created':
                self._handle_order_created(config, event_data)
            elif event_type == 'order.updated':
                self._handle_order_updated(config, event_data)
            elif event_type == 'order.deleted':
                self._handle_order_deleted(config, event_data)
            else:
                _logger.warning('Unknown event type: %s', event_type)
                return {'status': 'warning', 'message': f'Unknown event type: {event_type}'}

            return {'status': 'success', 'message': 'Webhook processed'}

        except Exception as e:
            _logger.error('Webhook processing failed: %s', str(e), exc_info=True)

            # Log error
            request.env['dotykacka.sync.log'].sudo().create({
                'config_id': config_id,
                'log_type': 'error',
                'direction': 'incoming',
                'endpoint': '/dotykacka/webhook',
                'status_code': 500,
                'error_message': str(e),
            })

            return {'status': 'error', 'message': str(e)}

    def _validate_signature(self, req, secret):
        """
        Validate webhook signature.

        Args:
            req: HTTP request
            secret (str): Webhook secret

        Returns:
            bool: True if signature is valid
        """
        try:
            # Get signature from header
            signature = req.httprequest.headers.get('X-Dotykacka-Signature')
            if not signature:
                return False

            # Calculate expected signature
            body = req.httprequest.get_data()
            expected_signature = hmac.new(
                secret.encode('utf-8'),
                body,
                hashlib.sha256
            ).hexdigest()

            # Compare signatures
            return hmac.compare_digest(signature, expected_signature)

        except Exception as e:
            _logger.error('Signature validation failed: %s', str(e))
            return False

    def _handle_order_created(self, config, event_data):
        """
        Handle order.created event.

        Args:
            config (dotykacka.config): Configuration
            event_data (dict): Event data
        """
        order_id = event_data.get('id')
        if not order_id:
            _logger.error('Order ID missing in event data')
            return

        try:
            # Create order sync instance
            order_sync = request.env['dotykacka.order.sync'].sudo().create({
                'config_id': config.id,
            })

            # Fetch and sync order
            order_sync.sync_order(event_data)

            _logger.info('Order created webhook processed: %s', order_id)

        except Exception as e:
            _logger.error('Failed to process order.created: %s', str(e))
            raise

    def _handle_order_updated(self, config, event_data):
        """
        Handle order.updated event.

        Args:
            config (dotykacka.config): Configuration
            event_data (dict): Event data
        """
        order_id = event_data.get('id')
        if not order_id:
            _logger.error('Order ID missing in event data')
            return

        try:
            # Create order sync instance
            order_sync = request.env['dotykacka.order.sync'].sudo().create({
                'config_id': config.id,
            })

            # Sync order update
            order_sync.sync_order(event_data)

            _logger.info('Order updated webhook processed: %s', order_id)

        except Exception as e:
            _logger.error('Failed to process order.updated: %s', str(e))
            raise

    def _handle_order_deleted(self, config, event_data):
        """
        Handle order.deleted event.

        Args:
            config (dotykacka.config): Configuration
            event_data (dict): Event data
        """
        order_id = event_data.get('id')
        if not order_id:
            _logger.error('Order ID missing in event data')
            return

        try:
            # Create order sync instance
            order_sync = request.env['dotykacka.order.sync'].sudo().create({
                'config_id': config.id,
            })

            # Handle order deletion
            order_sync.handle_order_deletion(str(order_id))

            _logger.info('Order deleted webhook processed: %s', order_id)

        except Exception as e:
            _logger.error('Failed to process order.deleted: %s', str(e))
            raise

    @http.route(
        '/dotykacka/webhook/test',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def webhook_test(self, **kwargs):
        """Test endpoint for webhook verification."""
        return {'status': 'success', 'message': 'Webhook endpoint is working'}
