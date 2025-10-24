"""Dotykacka OAuth 2.0 Integration."""

import logging
import requests
from datetime import datetime, timedelta
from odoo import _, api, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DotykackaOAuth(models.TransientModel):
    """Handle OAuth 2.0 flow for Dotykacka API."""

    _name = 'dotykacka.oauth'
    _description = 'Dotykacka OAuth Handler'

    @api.model
    def exchange_code_for_token(self, config, authorization_code):
        """
        Exchange authorization code for access token.

        :param config: dotykacka.config record
        :param authorization_code: Code received from OAuth callback
        :return: dict with access_token and refresh_token
        """
        token_url = 'https://api.dotykacka.cz/oauth/token'

        data = {
            'grant_type': 'authorization_code',
            'client_id': config.oauth_client_id,
            'client_secret': config.oauth_client_secret,
            'redirect_uri': config.oauth_redirect_uri,
            'code': authorization_code,
        }

        try:
            response = requests.post(token_url, data=data, timeout=30)
            response.raise_for_status()
            token_data = response.json()

            # Save tokens to config
            config.write({
                'access_token': token_data.get('access_token'),
                'refresh_token': token_data.get('refresh_token'),
                'token_expires_at': datetime.now() + timedelta(seconds=token_data.get('expires_in', 3600)),
            })

            _logger.info(f"OAuth tokens obtained successfully for config: {config.name}")

            return token_data

        except requests.exceptions.RequestException as e:
            _logger.error(f"OAuth token exchange failed: {str(e)}")
            raise ValidationError(_('Failed to obtain OAuth tokens: %s') % str(e))

    @api.model
    def refresh_access_token(self, config):
        """
        Refresh access token using refresh token.

        :param config: dotykacka.config record
        :return: dict with new access_token
        """
        if not config.refresh_token:
            raise ValidationError(_('No refresh token available. Please authorize again.'))

        token_url = 'https://api.dotykacka.cz/oauth/token'

        data = {
            'grant_type': 'refresh_token',
            'client_id': config.oauth_client_id,
            'client_secret': config.oauth_client_secret,
            'refresh_token': config.refresh_token,
        }

        try:
            response = requests.post(token_url, data=data, timeout=30)
            response.raise_for_status()
            token_data = response.json()

            # Update access token
            config.write({
                'access_token': token_data.get('access_token'),
                'token_expires_at': datetime.now() + timedelta(seconds=token_data.get('expires_in', 3600)),
            })

            _logger.info(f"Access token refreshed for config: {config.name}")

            return token_data

        except requests.exceptions.RequestException as e:
            _logger.error(f"Token refresh failed: {str(e)}")
            raise ValidationError(_('Failed to refresh access token: %s') % str(e))

    @api.model
    def ensure_valid_token(self, config):
        """
        Ensure access token is valid, refresh if needed.

        :param config: dotykacka.config record
        :return: valid access_token
        """
        if not config.access_token:
            raise ValidationError(_('No access token available. Please authorize first.'))

        # Check if token is expired or will expire in next 5 minutes
        if config.token_expires_at:
            expires_soon = datetime.now() + timedelta(minutes=5)
            if config.token_expires_at <= expires_soon:
                _logger.info(f"Token expired or expiring soon, refreshing for config: {config.name}")
                self.refresh_access_token(config)

        return config.access_token

    @api.model
    def revoke_token(self, config):
        """
        Revoke access token.

        :param config: dotykacka.config record
        """
        if not config.access_token:
            return

        revoke_url = 'https://api.dotykacka.cz/oauth/revoke'

        data = {
            'client_id': config.oauth_client_id,
            'client_secret': config.oauth_client_secret,
            'token': config.access_token,
        }

        try:
            response = requests.post(revoke_url, data=data, timeout=30)
            response.raise_for_status()

            # Clear tokens
            config.write({
                'access_token': False,
                'refresh_token': False,
                'token_expires_at': False,
            })

            _logger.info(f"Token revoked for config: {config.name}")

        except requests.exceptions.RequestException as e:
            _logger.warning(f"Token revocation failed: {str(e)}")
