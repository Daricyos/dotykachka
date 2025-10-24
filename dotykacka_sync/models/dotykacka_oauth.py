import json
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DotykackaOAuth(models.TransientModel):
    """OAuth 2.0 handler for Dotykačka API using api_manager."""

    _name = 'dotykacka.oauth'
    _description = 'Dotykačka OAuth Handler'

    config_id = fields.Many2one(
        'dotykacka.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
    )

    def _get_oauth_request(self):
        """Get OAuth token refresh request from api_manager."""
        request = self.env['api_manager.request'].search([
            ('name', '=', 'Refresh Access Token'),
        ], limit=1)

        if not request:
            raise UserError(_('OAuth request not found in api_manager. Please check module installation.'))

        return request

    def _get_api_request(self, request_name):
        """
        Get API request by name from api_manager.

        Args:
            request_name (str): Request name

        Returns:
            api_manager.request: Request record
        """
        request = self.env['api_manager.request'].search([
            ('name', '=', request_name),
        ], limit=1)

        if not request:
            raise UserError(_('API request "%s" not found in api_manager.') % request_name)

        return request

    def refresh_access_token(self):
        """
        Refresh the access token using refresh_token or initial OAuth flow.

        Returns:
            dict: Token response from Dotykačka
        """
        self.ensure_one()
        config = self.config_id

        # Prepare request payload
        if config.refresh_token:
            # Use refresh token to get new access token
            payload = {
                'grantType': 'refreshToken',
                'clientId': config.client_id,
                'clientSecret': config.client_secret,
                'refreshToken': config.refresh_token,
            }
        else:
            # Initial OAuth flow using client credentials
            payload = {
                'grantType': 'clientCredentials',
                'clientId': config.client_id,
                'clientSecret': config.client_secret,
            }

        try:
            # Get OAuth request from api_manager
            oauth_request = self._get_oauth_request()

            # Execute request
            oauth_request.send_request(data=payload, return_type='decoded')

            # Get response
            if not oauth_request.success:
                raise UserError(_('OAuth token refresh failed: %s') % oauth_request.error)

            token_data = oauth_request.decode_response()

            # Validate response
            if 'accessToken' not in token_data:
                raise UserError(_('Invalid token response: accessToken not found'))

            # Calculate token expiration (default 3600 seconds if not provided)
            expires_in = token_data.get('expiresIn', 3600)
            expires_at = datetime.now() + timedelta(seconds=expires_in)

            # Update configuration with new tokens
            update_vals = {
                'access_token': token_data['accessToken'],
                'token_expires_at': expires_at,
            }

            if 'refreshToken' in token_data:
                update_vals['refresh_token'] = token_data['refreshToken']

            config.write(update_vals)

            # Update token in api_manager provider
            self._update_provider_token(token_data['accessToken'])

            # Log the token refresh
            self.env['dotykacka.sync.log'].create({
                'config_id': config.id,
                'log_type': 'auth',
                'direction': 'outgoing',
                'endpoint': oauth_request.url_path,
                'status_code': oauth_request.status_code,
                'request_data': json.dumps({
                    'grantType': payload['grantType'],
                    'clientId': payload['clientId'],
                }),
                'response_data': json.dumps({
                    'accessToken': '***',
                    'refreshToken': '***' if 'refreshToken' in token_data else None,
                    'expiresIn': expires_in,
                }),
            })

            return token_data

        except Exception as e:
            error_msg = _('OAuth token refresh failed: %s') % str(e)
            _logger.error(error_msg)

            # Log the error
            self.env['dotykacka.sync.log'].create({
                'config_id': config.id,
                'log_type': 'auth',
                'direction': 'outgoing',
                'endpoint': '/v2/signin/token',
                'status_code': 0,
                'error_message': str(e),
            })

            raise UserError(error_msg)

    def _update_provider_token(self, access_token):
        """
        Update bearer token in api_manager provider.

        Args:
            access_token (str): New access token
        """
        # Find the API provider
        provider = self.env['api_manager.provider'].search([
            ('internal_reference', '=', 'DKSYNC_API'),
        ], limit=1)

        if provider:
            # Update token in provider
            provider.write({'token': access_token})

            # Or update via request parameter for company-specific token
            param = self.env['api_manager.request_parameter'].search([
                ('provider', '=', provider.id),
                ('key', '=', 'token'),
                ('company_id', '=', self.config_id.company_id.id),
            ])

            if param:
                param.write({'value': access_token})
            else:
                self.env['api_manager.request_parameter'].create({
                    'provider': provider.id,
                    'key': 'token',
                    'value': access_token,
                    'company_id': self.config_id.company_id.id,
                })

    def ensure_valid_token(self):
        """
        Ensure we have a valid access token, refresh if needed.

        Returns:
            str: Valid access token
        """
        self.ensure_one()
        config = self.config_id

        # Check if token exists and is not expired
        if config.access_token and config.token_expires_at:
            # Add 5 minute buffer before expiration
            if datetime.now() < (config.token_expires_at - timedelta(minutes=5)):
                return config.access_token

        # Token doesn't exist or is expired, refresh it
        self.refresh_access_token()
        return config.access_token

    def call_api(self, method, endpoint, data=None, params=None, retry=True):
        """
        Make an authenticated API call to Dotykačka using api_manager.

        Args:
            method (str): HTTP method (GET, POST, PUT, PATCH, DELETE)
            endpoint (str): API endpoint path (e.g., '/v2/clouds/{cloud_id}/orders')
            data (dict): Request payload for POST/PUT/PATCH
            params (dict): Query parameters
            retry (bool): Whether to retry on token expiration

        Returns:
            dict: API response data
        """
        self.ensure_one()
        config = self.config_id

        # Ensure we have a valid token
        self.ensure_valid_token()

        try:
            # Find appropriate request in api_manager based on endpoint
            api_request = self._find_request_by_endpoint(endpoint, method)

            if not api_request:
                # Fallback: use generic GET request if available
                _logger.warning('No specific request found for endpoint %s, using generic approach', endpoint)
                return self._call_api_generic(method, endpoint, data, params)

            # Prepare URL parameters
            url_params = self._extract_url_params(endpoint)

            # Execute request
            api_request.send_request(
                params=url_params,
                args=params or {},
                data=data,
                return_type='decoded'
            )

            # Check success
            if not api_request.success:
                # Handle token expiration
                if api_request.status_code == 401 and retry:
                    _logger.info('Token expired, refreshing...')
                    self.refresh_access_token()
                    return self.call_api(method, endpoint, data, params, retry=False)

                raise UserError(
                    _('API call failed: %s - %s') % (api_request.status_code, api_request.error)
                )

            # Log the request
            self.env['dotykacka.sync.log'].create({
                'config_id': config.id,
                'log_type': 'api',
                'direction': 'outgoing',
                'endpoint': endpoint,
                'status_code': api_request.status_code,
                'request_data': json.dumps(data) if data else None,
                'response_data': str(api_request.decode_response())[:5000],
            })

            return api_request.decode_response()

        except Exception as e:
            error_msg = _('API request failed: %s') % str(e)
            _logger.error(error_msg)

            # Log the error
            self.env['dotykacka.sync.log'].create({
                'config_id': config.id,
                'log_type': 'error',
                'direction': 'outgoing',
                'endpoint': endpoint,
                'status_code': 0,
                'error_message': str(e),
            })

            raise UserError(error_msg)

    def _find_request_by_endpoint(self, endpoint, method):
        """
        Find api_manager request by endpoint pattern.

        Args:
            endpoint (str): Endpoint path
            method (str): HTTP method

        Returns:
            api_manager.request: Request record or None
        """
        # Map endpoints to request names
        endpoint_map = {
            'customers': 'Get Customers',
            'customers/': 'Get Customer',
            'products': 'Get Products',
            'products/': 'Get Product',
            'orders': 'Get Orders',
            'orders/': 'Get Order',
            'branches': 'Get Branches',
            'webhooks': 'Register Webhook',
        }

        # Find matching pattern
        for pattern, request_name in endpoint_map.items():
            if pattern in endpoint:
                request = self.env['api_manager.request'].search([
                    ('name', '=', request_name),
                ], limit=1)
                if request:
                    return request

        return None

    def _extract_url_params(self, endpoint):
        """
        Extract URL parameters from endpoint.

        Args:
            endpoint (str): Endpoint with parameters like /v2/clouds/{cloud_id}/orders

        Returns:
            dict: URL parameters
        """
        params = {}

        # Extract cloud_id
        if '{cloud_id}' in endpoint or '/clouds/' in endpoint:
            params['cloud_id'] = self.config_id.cloud_id

        # Extract other IDs from endpoint
        parts = endpoint.split('/')
        for i, part in enumerate(parts):
            if i > 0 and not part.startswith('{'):
                prev_part = parts[i-1]
                if prev_part in ['customers', 'products', 'orders', 'branches']:
                    params[f'{prev_part[:-1]}_id'] = part

        return params

    def _call_api_generic(self, method, endpoint, data=None, params=None):
        """
        Generic API call when specific request is not found.
        This is a fallback that creates a temporary request.

        Args:
            method (str): HTTP method
            endpoint (str): Endpoint path
            data (dict): Request data
            params (dict): Query parameters

        Returns:
            dict: Response data
        """
        # Get API provider
        provider = self.env['api_manager.provider'].search([
            ('internal_reference', '=', 'DKSYNC_API'),
        ], limit=1)

        if not provider:
            raise UserError(_('Dotykačka API provider not found'))

        # Create temporary request
        temp_request = self.env['api_manager.request'].create({
            'name': f'Temp: {method} {endpoint}',
            'provider': provider.id,
            'method': method.lower(),
            'url_path': endpoint,
            'content_type': 'application/json',
        })

        # Execute request
        url_params = self._extract_url_params(endpoint)
        temp_request.send_request(
            params=url_params,
            args=params or {},
            data=data,
            return_type='decoded'
        )

        response = temp_request.decode_response()

        # Delete temporary request
        temp_request.unlink()

        return response

    def call_api_paginated(self, method, endpoint, params=None, page_size=100):
        """
        Make paginated API calls to Dotykačka.

        Args:
            method (str): HTTP method (typically GET)
            endpoint (str): API endpoint path
            params (dict): Query parameters
            page_size (int): Number of items per page

        Yields:
            dict: Each item from all pages
        """
        self.ensure_one()
        params = params or {}
        params['limit'] = page_size
        params['offset'] = 0

        while True:
            response = self.call_api(method, endpoint, params=params)

            # Handle different response structures
            data = response.get('data', [])
            if not data:
                break

            for item in data:
                yield item

            # Check if there are more pages
            if len(data) < page_size:
                break

            params['offset'] += page_size
