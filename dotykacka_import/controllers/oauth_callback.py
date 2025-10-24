"""OAuth Callback Controller."""

import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class DotykackaOAuthCallbackController(http.Controller):
    """Handle OAuth 2.0 callbacks from Dotykacka."""

    @http.route(
        '/dotykacka/oauth/callback',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
    )
    def oauth_callback(self, **kwargs):
        """
        OAuth callback endpoint.

        Expected parameters:
        - code: Authorization code
        - state: Config ID
        - error: Error code (if authorization failed)
        - error_description: Error description
        """
        code = kwargs.get('code')
        state = kwargs.get('state')  # This should be config_id
        error = kwargs.get('error')
        error_description = kwargs.get('error_description')

        if error:
            _logger.error(f"OAuth error: {error} - {error_description}")
            return request.render('dotykacka_import.oauth_error', {
                'error': error,
                'error_description': error_description,
            })

        if not code or not state:
            _logger.error("Missing code or state parameter")
            return request.render('dotykacka_import.oauth_error', {
                'error': 'invalid_request',
                'error_description': 'Missing required parameters',
            })

        try:
            config_id = int(state)
            config = request.env['dotykacka.config'].sudo().browse(config_id)

            if not config.exists():
                _logger.error(f"Config not found: {config_id}")
                return request.render('dotykacka_import.oauth_error', {
                    'error': 'invalid_state',
                    'error_description': 'Invalid configuration ID',
                })

            # Exchange code for tokens
            oauth = request.env['dotykacka.oauth'].sudo()
            oauth.exchange_code_for_token(config, code)

            _logger.info(f"OAuth tokens obtained for config: {config.name}")

            return request.render('dotykacka_import.oauth_success', {
                'config_name': config.name,
            })

        except Exception as e:
            _logger.error(f"Error in OAuth callback: {str(e)}", exc_info=True)
            return request.render('dotykacka_import.oauth_error', {
                'error': 'token_exchange_failed',
                'error_description': str(e),
            })
