"""OAuth Service for Dotykačka API."""

import logging
import requests
from urllib.parse import urlencode

from odoo import _, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DotykackaOAuthService(models.AbstractModel):
    """Service for handling OAuth 2.0 authentication with Dotykačka API."""

    _name = 'dotykacka.oauth.service'
    _description = 'Dotykačka OAuth Service'

    def get_authorization_url(self, config):
        """
        Generate OAuth authorization URL.

        Args:
            config: dotykacka.config record

        Returns:
            str: Authorization URL
        """
        self.ensure_one()

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        redirect_uri = f"{base_url}/dotykacka/oauth/callback"

        params = {
            'client_id': config.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'openid profile email offline_access',
            'state': str(config.id),  # Store config ID in state
        }

        auth_url = f"{config.api_base_url}/oauth/authorize"
        return f"{auth_url}?{urlencode(params)}"

    def exchange_code_for_token(self, config, authorization_code):
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            config: dotykacka.config record
            authorization_code: Authorization code from OAuth callback

        Returns:
            dict: Token data including access_token and refresh_token

        Raises:
            ValidationError: If token exchange fails
        """
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        redirect_uri = f"{base_url}/dotykacka/oauth/callback"

        token_url = f"{config.api_base_url}/oauth/token"

        data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'client_id': config.client_id,
            'client_secret': config.client_secret,
            'redirect_uri': redirect_uri,
        }

        try:
            response = requests.post(token_url, data=data, timeout=30)
            response.raise_for_status()

            token_data = response.json()

            # Create OAuth token record
            oauth_token = self.env['dotykacka.oauth'].create({
                'config_id': config.id,
                'access_token': token_data['access_token'],
                'refresh_token': token_data.get('refresh_token'),
                'token_type': token_data.get('token_type', 'Bearer'),
                'expires_in': token_data.get('expires_in', 3600),
                'scope': token_data.get('scope', ''),
            })

            _logger.info(
                'OAuth token obtained successfully for config %s',
                config.cloud_id
            )

            return token_data

        except requests.exceptions.RequestException as e:
            _logger.error('Failed to exchange authorization code: %s', str(e))
            raise ValidationError(_(
                'Failed to obtain access token: %s'
            ) % str(e))

    def refresh_token(self, config, refresh_token):
        """
        Refresh access token using refresh token.

        Args:
            config: dotykacka.config record
            refresh_token: Refresh token

        Returns:
            dict: New token data

        Raises:
            ValidationError: If token refresh fails
        """
        token_url = f"{config.api_base_url}/oauth/token"

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': config.client_id,
            'client_secret': config.client_secret,
        }

        try:
            response = requests.post(token_url, data=data, timeout=30)
            response.raise_for_status()

            token_data = response.json()

            _logger.info(
                'OAuth token refreshed successfully for config %s',
                config.cloud_id
            )

            return token_data

        except requests.exceptions.RequestException as e:
            _logger.error('Failed to refresh token: %s', str(e))
            raise ValidationError(_(
                'Failed to refresh access token: %s\n'
                'Please re-authenticate.'
            ) % str(e))

    def revoke_token(self, config, token):
        """
        Revoke access token.

        Args:
            config: dotykacka.config record
            token: Token to revoke

        Returns:
            bool: True if successful
        """
        revoke_url = f"{config.api_base_url}/oauth/revoke"

        data = {
            'token': token,
            'client_id': config.client_id,
            'client_secret': config.client_secret,
        }

        try:
            response = requests.post(revoke_url, data=data, timeout=30)
            response.raise_for_status()

            _logger.info('Token revoked successfully for config %s', config.cloud_id)
            return True

        except requests.exceptions.RequestException as e:
            _logger.warning('Failed to revoke token: %s', str(e))
            return False
