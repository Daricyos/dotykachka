"""Dotykačka API Client."""

import logging
import json

from odoo import _, api, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DotykackaAPI(models.AbstractModel):
    """API Client for Dotykačka/Dotypos API v2."""

    _name = 'dotykacka.api'
    _description = 'Dotykačka API Client'

    @api.model
    def create_client(self, config):
        """
        Factory method to create API client instance.

        Args:
            config: dotykacka.config record

        Returns:
            DotykackaAPIClient: API client instance
        """
        return DotykackaAPIClient(self.env, config)


class DotykackaAPIClient:
    """
    Dotykačka API Client implementation.

    This is a wrapper around api_manager that provides convenient methods
    for Dotykačka API operations with automatic token management and rate limiting.
    """

    def __init__(self, env, config):
        """
        Initialize API client.

        Args:
            env: Odoo environment
            config: dotykacka.config record
        """
        self.env = env
        self.config = config
        self.rate_limiter = env['dotykacka.rate.limiter']

    def _get_access_token(self):
        """Get valid access token, refreshing if necessary."""
        if not self.config.oauth_id:
            raise ValidationError(_('Not authenticated. Please authorize with Dotykačka first.'))

        return self.config.oauth_id.get_valid_token()

    def _get_api_request(self, request_name):
        """
        Get API request record by name.

        Args:
            request_name: Internal reference name for request

        Returns:
            api_manager.request: Request record
        """
        request = self.env['api_manager.request'].search([
            ('provider', '=', self.config.api_provider_id.id),
            ('name', '=', request_name),
        ], limit=1)

        if not request:
            raise ValidationError(_(
                'API request "%s" not found. Please check module configuration.'
            ) % request_name)

        return request

    def _make_request(self, request_name, **kwargs):
        """
        Make API request with rate limiting and token management.

        Args:
            request_name: Name of API request
            **kwargs: Request parameters (params, args, data, headers)

        Returns:
            dict: Response data

        Raises:
            ValidationError: If request fails
        """
        # Check rate limit and wait if needed
        self.rate_limiter.wait_if_needed(self.config)

        # Get valid access token
        access_token = self._get_access_token()

        # Get request template
        request = self._get_api_request(request_name)

        # Prepare headers with auth token
        headers = kwargs.get('headers', {})
        headers['Authorization'] = f'Bearer {access_token}'
        kwargs['headers'] = headers

        # Make request
        success = request.send_request(return_type='success', **kwargs)

        # Record request for rate limiting
        self.rate_limiter.record_request(self.config)

        if not success:
            error_msg = request.message or 'Unknown error'
            _logger.error(
                'API request %s failed: %s (status: %s)',
                request_name,
                error_msg,
                request.status_code
            )
            raise ValidationError(_(
                'API request failed: %s\nStatus: %s'
            ) % (error_msg, request.status_code))

        return request.decode_response()

    # ============== Cloud & Account ==============

    def get_cloud_info(self):
        """
        Get cloud information.

        Returns:
            dict: Cloud data
        """
        return self._make_request(
            'get_cloud',
            params={'{cloudId}': self.config.cloud_id}
        )

    def test_connection(self):
        """
        Test API connection.

        Returns:
            dict: Cloud info if successful
        """
        return self.get_cloud_info()

    # ============== Customers ==============

    def get_customers(self, limit=100, offset=0):
        """
        Get customers from Dotykačka.

        Args:
            limit: Number of records to fetch
            offset: Offset for pagination

        Returns:
            dict: Customer data
        """
        return self._make_request(
            'get_customers',
            params={'{cloudId}': self.config.cloud_id},
            args={'limit': str(limit), 'offset': str(offset)}
        )

    def get_customer(self, customer_id):
        """
        Get single customer by ID.

        Args:
            customer_id: Customer ID in Dotykačka

        Returns:
            dict: Customer data
        """
        return self._make_request(
            'get_customer',
            params={
                '{cloudId}': self.config.cloud_id,
                '{customerId}': str(customer_id)
            }
        )

    # ============== Products ==============

    def get_products(self, limit=100, offset=0):
        """
        Get products from Dotykačka.

        Args:
            limit: Number of records to fetch
            offset: Offset for pagination

        Returns:
            dict: Product data
        """
        return self._make_request(
            'get_products',
            params={'{cloudId}': self.config.cloud_id},
            args={'limit': str(limit), 'offset': str(offset)}
        )

    def get_product(self, product_id):
        """
        Get single product by ID.

        Args:
            product_id: Product ID in Dotykačka

        Returns:
            dict: Product data
        """
        return self._make_request(
            'get_product',
            params={
                '{cloudId}': self.config.cloud_id,
                '{productId}': str(product_id)
            }
        )

    # ============== Orders/Receipts ==============

    def get_orders(self, limit=100, offset=0, date_from=None, date_to=None):
        """
        Get orders/receipts from Dotykačka.

        Args:
            limit: Number of records to fetch
            offset: Offset for pagination
            date_from: Filter from date (YYYY-MM-DD)
            date_to: Filter to date (YYYY-MM-DD)

        Returns:
            dict: Order data
        """
        args = {
            'limit': str(limit),
            'offset': str(offset)
        }

        if date_from:
            args['dateFrom'] = date_from
        if date_to:
            args['dateTo'] = date_to

        return self._make_request(
            'get_orders',
            params={'{cloudId}': self.config.cloud_id},
            args=args
        )

    def get_order(self, order_id):
        """
        Get single order/receipt by ID.

        Args:
            order_id: Order/Receipt ID in Dotykačka

        Returns:
            dict: Order data
        """
        return self._make_request(
            'get_order',
            params={
                '{cloudId}': self.config.cloud_id,
                '{orderId}': str(order_id)
            }
        )

    # ============== Webhooks ==============

    def register_webhook(self, webhook_url, events=None):
        """
        Register webhook in Dotykačka.

        Args:
            webhook_url: URL where webhook events will be sent
            events: List of event types to subscribe to

        Returns:
            str: Webhook ID
        """
        if events is None:
            events = ['order.created', 'order.updated', 'order.deleted']

        data = {
            'url': webhook_url,
            'events': events,
            'active': True
        }

        response = self._make_request(
            'create_webhook',
            params={'{cloudId}': self.config.cloud_id},
            data=data
        )

        return response.get('id')

    def unregister_webhook(self, webhook_id):
        """
        Unregister webhook from Dotykačka.

        Args:
            webhook_id: Webhook ID to delete

        Returns:
            bool: True if successful
        """
        self._make_request(
            'delete_webhook',
            params={
                '{cloudId}': self.config.cloud_id,
                '{webhookId}': str(webhook_id)
            }
        )
        return True

    def get_webhooks(self):
        """
        Get all registered webhooks.

        Returns:
            list: List of webhook configurations
        """
        response = self._make_request(
            'get_webhooks',
            params={'{cloudId}': self.config.cloud_id}
        )
        return response.get('data', [])

    # ============== Payment Methods ==============

    def get_payment_methods(self):
        """
        Get available payment methods.

        Returns:
            list: Payment methods
        """
        response = self._make_request(
            'get_payment_methods',
            params={'{cloudId}': self.config.cloud_id}
        )
        return response.get('data', [])

    # ============== Employees/Salespeople ==============

    def get_employees(self, limit=100, offset=0):
        """
        Get employees (salespeople) from Dotykačka.

        Args:
            limit: Number of records to fetch
            offset: Offset for pagination

        Returns:
            dict: Employee data
        """
        return self._make_request(
            'get_employees',
            params={'{cloudId}': self.config.cloud_id},
            args={'limit': str(limit), 'offset': str(offset)}
        )
