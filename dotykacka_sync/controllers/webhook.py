"""Webhook Controller for Dotykačka events."""

import logging
import json

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class DotykackaWebhook(http.Controller):
    """Controller for handling webhook events from Dotykačka."""

    @http.route('/dotykacka/webhook/<string:cloud_id>', type='json', auth='none', methods=['POST'], csrf=False)
    def webhook_event(self, cloud_id, **kwargs):
        """
        Handle webhook event from Dotykačka.

        Args:
            cloud_id: Cloud ID from URL path

        Returns:
            dict: Response with status
        """
        try:
            # Get request data
            data = request.jsonrequest

            _logger.info('Received webhook event for cloud %s: %s', cloud_id, data.get('event'))

            # Find configuration
            config = request.env['dotykacka.config'].sudo().search([
                ('cloud_id', '=', cloud_id),
                ('active', '=', True),
            ], limit=1)

            if not config:
                _logger.warning('No configuration found for cloud %s', cloud_id)
                return {'status': 'error', 'message': 'Configuration not found'}

            # Validate webhook is registered
            if not config.webhook_active or not config.webhook_id:
                _logger.warning('Webhook not active for cloud %s', cloud_id)
                return {'status': 'error', 'message': 'Webhook not active'}

            # Process event
            result = self._process_event(config, data)

            return {'status': 'success', 'result': result}

        except Exception as e:
            _logger.error('Error processing webhook: %s', str(e), exc_info=True)
            return {'status': 'error', 'message': str(e)}

    @http.route('/dotykacka/oauth/callback', type='http', auth='none', methods=['GET'], csrf=False)
    def oauth_callback(self, **kwargs):
        """
        Handle OAuth callback from Dotykačka.

        Args:
            **kwargs: Query parameters including 'code' and 'state'

        Returns:
            Response: HTML response
        """
        try:
            code = kwargs.get('code')
            state = kwargs.get('state')
            error = kwargs.get('error')

            if error:
                _logger.error('OAuth error: %s', kwargs.get('error_description', error))
                return request.render('dotykacka_sync.oauth_error', {
                    'error': error,
                    'description': kwargs.get('error_description', 'Unknown error')
                })

            if not code or not state:
                return request.render('dotykacka_sync.oauth_error', {
                    'error': 'missing_parameters',
                    'description': 'Missing authorization code or state'
                })

            # Get configuration from state
            try:
                config_id = int(state)
            except ValueError:
                return request.render('dotykacka_sync.oauth_error', {
                    'error': 'invalid_state',
                    'description': 'Invalid state parameter'
                })

            config = request.env['dotykacka.config'].sudo().browse(config_id)

            if not config.exists():
                return request.render('dotykacka_sync.oauth_error', {
                    'error': 'config_not_found',
                    'description': 'Configuration not found'
                })

            # Exchange code for token
            oauth_service = request.env['dotykacka.oauth.service'].sudo()
            token_data = oauth_service.exchange_code_for_token(config, code)

            # Render success page
            return request.render('dotykacka_sync.oauth_success', {
                'config': config,
            })

        except Exception as e:
            _logger.error('OAuth callback error: %s', str(e), exc_info=True)
            return request.render('dotykacka_sync.oauth_error', {
                'error': 'exception',
                'description': str(e)
            })

    def _process_event(self, config, data):
        """
        Process webhook event.

        Args:
            config: dotykacka.config record
            data: Event data

        Returns:
            dict: Processing result
        """
        event_type = data.get('event')
        entity_type = data.get('entityType')
        entity_id = data.get('entityId')
        entity_data = data.get('data', {})

        _logger.info(
            'Processing event %s for %s %s',
            event_type,
            entity_type,
            entity_id
        )

        # Log webhook event
        request.env['dotykacka.sync.log'].sudo().create({
            'config_id': config.id,
            'sync_type': 'webhook',
            'sync_action': event_type,
            'sync_status': 'success',
            'message': f"Webhook event received: {event_type} for {entity_type} {entity_id}",
            'dotykacka_id': str(entity_id),
            'dotykacka_type': entity_type,
            'webhook_payload': json.dumps(data),
            'triggered_by': 'webhook',
        })

        # Route to appropriate handler
        if entity_type == 'order' or entity_type == 'receipt':
            return self._handle_order_event(config, event_type, entity_id, entity_data)
        elif entity_type == 'customer':
            return self._handle_customer_event(config, event_type, entity_id, entity_data)
        elif entity_type == 'product':
            return self._handle_product_event(config, event_type, entity_id, entity_data)
        else:
            _logger.info('Unhandled entity type: %s', entity_type)
            return {'message': f'Entity type {entity_type} not handled'}

    def _handle_order_event(self, config, event_type, entity_id, entity_data):
        """
        Handle order webhook event.

        Args:
            config: dotykacka.config record
            event_type: Event type (created, updated, deleted)
            entity_id: Order ID
            entity_data: Order data

        Returns:
            dict: Result
        """
        try:
            if event_type in ['created', 'updated']:
                # Sync order
                order_sync = request.env['dotykacka.sync.order'].sudo()
                sale_order = order_sync.sync_order_by_id(config, entity_id)

                return {
                    'action': 'synced',
                    'order_id': sale_order.id if sale_order else None,
                    'order_name': sale_order.name if sale_order else None
                }

            elif event_type == 'deleted':
                # Handle deleted order
                mapping = request.env['dotykacka.order.mapping'].sudo().search([
                    ('config_id', '=', config.id),
                    ('dotykacka_receipt_id', '=', str(entity_id)),
                ], limit=1)

                if mapping:
                    mapping.action_cancel_order()
                    return {'action': 'cancelled'}
                else:
                    return {'action': 'not_found'}

            else:
                return {'action': 'ignored', 'reason': f'Unknown event type: {event_type}'}

        except Exception as e:
            _logger.error('Error handling order event: %s', str(e), exc_info=True)
            raise

    def _handle_customer_event(self, config, event_type, entity_id, entity_data):
        """
        Handle customer webhook event.

        Args:
            config: dotykacka.config record
            event_type: Event type
            entity_id: Customer ID
            entity_data: Customer data

        Returns:
            dict: Result
        """
        try:
            if event_type in ['created', 'updated']:
                customer_sync = request.env['dotykacka.sync.customer'].sudo()
                partner = customer_sync.sync_customer_by_id(config, entity_id)

                return {
                    'action': 'synced',
                    'partner_id': partner.id if partner else None,
                    'partner_name': partner.name if partner else None
                }

            elif event_type == 'deleted':
                # Mark customer as inactive or delete
                partner = request.env['res.partner'].sudo().search([
                    ('dotykacka_customer_id', '=', str(entity_id))
                ], limit=1)

                if partner:
                    partner.write({'active': False})
                    return {'action': 'deactivated'}
                else:
                    return {'action': 'not_found'}

            else:
                return {'action': 'ignored', 'reason': f'Unknown event type: {event_type}'}

        except Exception as e:
            _logger.error('Error handling customer event: %s', str(e), exc_info=True)
            raise

    def _handle_product_event(self, config, event_type, entity_id, entity_data):
        """
        Handle product webhook event.

        Args:
            config: dotykacka.config record
            event_type: Event type
            entity_id: Product ID
            entity_data: Product data

        Returns:
            dict: Result
        """
        try:
            if event_type in ['created', 'updated']:
                product_sync = request.env['dotykacka.sync.product'].sudo()
                product = product_sync.sync_product_by_id(config, entity_id)

                return {
                    'action': 'synced',
                    'product_id': product.id if product else None,
                    'product_name': product.name if product else None
                }

            elif event_type == 'deleted':
                # Mark product as inactive or delete
                product = request.env['product.product'].sudo().search([
                    ('dotykacka_product_id', '=', str(entity_id))
                ], limit=1)

                if product:
                    product.write({'active': False})
                    return {'action': 'deactivated'}
                else:
                    return {'action': 'not_found'}

            else:
                return {'action': 'ignored', 'reason': f'Unknown event type: {event_type}'}

        except Exception as e:
            _logger.error('Error handling product event: %s', str(e), exc_info=True)
            raise
