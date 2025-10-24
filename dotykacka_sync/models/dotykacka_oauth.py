import requests
import json
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class DotykackaOAuth(models.TransientModel):
    """OAuth 2.0 handler for Dotykačka API."""

    _name = 'dotykacka.oauth'
    _description = 'Dotykačka OAuth Handler'

    config_id = fields.Many2one(
        'dotykacka.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
    )

    def _get_token_url(self):
        """Get token endpoint URL."""
        config = self.config_id
        return f"{config.api_base_url}/{config.api_version}/signin/token"

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
            # Make token request
            response = requests.post(
                self._get_token_url(),
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30,
            )

            response.raise_for_status()
            token_data = response.json()

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

            # Log the token refresh
            self.env['dotykacka.sync.log'].create({
                'config_id': config.id,
                'log_type': 'auth',
                'direction': 'outgoing',
                'endpoint': self._get_token_url(),
                'status_code': response.status_code,
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

        except requests.exceptions.RequestException as e:
            error_msg = _('OAuth token refresh failed: %s') % str(e)

            # Log the error
            self.env['dotykacka.sync.log'].create({
                'config_id': config.id,
                'log_type': 'auth',
                'direction': 'outgoing',
                'endpoint': self._get_token_url(),
                'status_code': getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0,
                'error_message': str(e),
            })

            raise UserError(error_msg)

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
        Make an authenticated API call to Dotykačka.

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
        access_token = self.ensure_valid_token()

        # Build full URL
        url = f"{config.api_base_url}{endpoint}"

        # Prepare headers
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }

        try:
            # Make the API call
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=headers,
                json=data,
                params=params,
                timeout=30,
            )

            # Log the request
            self.env['dotykacka.sync.log'].create({
                'config_id': config.id,
                'log_type': 'api',
                'direction': 'outgoing',
                'endpoint': endpoint,
                'status_code': response.status_code,
                'request_data': json.dumps(data) if data else None,
                'response_data': response.text[:5000] if response.text else None,  # Limit response size
            })

            # Handle token expiration (401) - retry once
            if response.status_code == 401 and retry:
                # Token might be expired, refresh and retry
                self.refresh_access_token()
                return self.call_api(method, endpoint, data, params, retry=False)

            response.raise_for_status()

            # Parse JSON response
            if response.content:
                return response.json()
            return {}

        except requests.exceptions.HTTPError as e:
            error_msg = _('API call failed: %s - %s') % (e.response.status_code, e.response.text)

            # Log the error
            self.env['dotykacka.sync.log'].create({
                'config_id': config.id,
                'log_type': 'api',
                'direction': 'outgoing',
                'endpoint': endpoint,
                'status_code': e.response.status_code if hasattr(e, 'response') else 0,
                'error_message': str(e),
                'response_data': e.response.text if hasattr(e, 'response') else None,
            })

            raise UserError(error_msg)

        except requests.exceptions.RequestException as e:
            error_msg = _('API request failed: %s') % str(e)

            # Log the error
            self.env['dotykacka.sync.log'].create({
                'config_id': config.id,
                'log_type': 'api',
                'direction': 'outgoing',
                'endpoint': endpoint,
                'status_code': 0,
                'error_message': str(e),
            })

            raise UserError(error_msg)

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

    def handle_rate_limit(self, response):
        """
        Handle API rate limiting.

        Dotykačka API has a limit of ~150 requests per 30 minutes.
        """
        # Check for rate limit headers
        if 'X-RateLimit-Remaining' in response.headers:
            remaining = int(response.headers['X-RateLimit-Remaining'])
            if remaining < 10:
                # Log warning when approaching rate limit
                self.env['dotykacka.sync.log'].create({
                    'config_id': self.config_id.id,
                    'log_type': 'warning',
                    'direction': 'outgoing',
                    'endpoint': 'rate_limit_warning',
                    'response_data': f'Rate limit remaining: {remaining}',
                })

        # If rate limited (429), raise user-friendly error
        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After', '1800')  # Default 30 min
            raise UserError(
                _('Dotykačka API rate limit exceeded. Please try again in %s seconds.') % retry_after
            )
