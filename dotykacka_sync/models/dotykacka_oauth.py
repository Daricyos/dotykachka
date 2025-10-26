"""Dotykačka OAuth Token Management."""

import logging
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DotykackaOAuth(models.Model):
    """OAuth Token Management for Dotykačka API."""

    _name = 'dotykacka.oauth'
    _description = 'Dotykačka OAuth Token'
    _order = 'create_date desc'

    config_id = fields.Many2one(
        'dotykacka.config',
        string='Configuration',
        required=True,
        ondelete='cascade'
    )
    company_id = fields.Many2one(
        related='config_id.company_id',
        string='Company',
        store=True,
        readonly=True
    )

    # OAuth Tokens
    access_token = fields.Char(
        string='Access Token',
        required=True,
        help='OAuth access token for API requests'
    )
    refresh_token = fields.Char(
        string='Refresh Token',
        help='OAuth refresh token to obtain new access tokens'
    )
    token_type = fields.Char(
        string='Token Type',
        default='Bearer',
        help='OAuth token type (usually Bearer)'
    )

    # Token Expiration
    expires_in = fields.Integer(
        string='Expires In (seconds)',
        help='Number of seconds until token expires'
    )
    expires_at = fields.Datetime(
        string='Expires At',
        compute='_compute_expires_at',
        store=True,
        help='Datetime when token expires'
    )
    is_valid = fields.Boolean(
        string='Is Valid',
        compute='_compute_is_valid',
        store=False,
        help='Check if token is still valid'
    )

    # Token Scope
    scope = fields.Char(
        string='Scope',
        help='OAuth scopes granted to this token'
    )

    # Metadata
    obtained_at = fields.Datetime(
        string='Obtained At',
        default=fields.Datetime.now,
        required=True,
        help='When this token was obtained'
    )
    last_refresh_at = fields.Datetime(
        string='Last Refresh',
        help='When this token was last refreshed'
    )
    refresh_count = fields.Integer(
        string='Refresh Count',
        default=0,
        help='Number of times this token has been refreshed'
    )

    # State
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Set to false when token is revoked or replaced'
    )

    @api.depends('obtained_at', 'expires_in')
    def _compute_expires_at(self):
        """Compute expiration datetime."""
        for record in self:
            if record.obtained_at and record.expires_in:
                record.expires_at = record.obtained_at + timedelta(seconds=record.expires_in)
            else:
                record.expires_at = False

    @api.depends('expires_at', 'active')
    def _compute_is_valid(self):
        """Check if token is still valid."""
        now = fields.Datetime.now()
        for record in self:
            if not record.active:
                record.is_valid = False
            elif not record.expires_at:
                # If no expiration, assume valid
                record.is_valid = True
            else:
                # Add 5 minute buffer before expiration
                buffer = timedelta(minutes=5)
                record.is_valid = record.expires_at > (now + buffer)

    def get_valid_token(self):
        """
        Get a valid access token, refreshing if necessary.

        Returns:
            str: Valid access token

        Raises:
            ValidationError: If unable to get valid token
        """
        self.ensure_one()

        if self.is_valid:
            return self.access_token

        if not self.refresh_token:
            raise ValidationError(_(
                'Access token expired and no refresh token available. '
                'Please re-authenticate.'
            ))

        # Token expired or about to expire, refresh it
        try:
            self.refresh_access_token()
            return self.access_token
        except Exception as e:
            _logger.error('Failed to refresh access token: %s', str(e))
            raise ValidationError(_(
                'Failed to refresh access token: %s\n'
                'Please re-authenticate.'
            ) % str(e))

    def refresh_access_token(self):
        """
        Refresh the access token using the refresh token.

        This method calls the OAuth service to get a new access token.
        """
        self.ensure_one()

        if not self.refresh_token:
            raise ValidationError(_('No refresh token available.'))

        # Call OAuth service to refresh token
        oauth_service = self.env['dotykacka.oauth.service']
        token_data = oauth_service.refresh_token(
            self.config_id,
            self.refresh_token
        )

        # Update token data
        self.write({
            'access_token': token_data['access_token'],
            'refresh_token': token_data.get('refresh_token', self.refresh_token),
            'expires_in': token_data.get('expires_in', self.expires_in),
            'token_type': token_data.get('token_type', self.token_type),
            'scope': token_data.get('scope', self.scope),
            'obtained_at': fields.Datetime.now(),
            'last_refresh_at': fields.Datetime.now(),
            'refresh_count': self.refresh_count + 1,
        })

        _logger.info(
            'OAuth token refreshed successfully for config %s (refresh count: %d)',
            self.config_id.cloud_id,
            self.refresh_count
        )

    def revoke_token(self):
        """
        Revoke this token.

        This marks the token as inactive and optionally calls the API to revoke it.
        """
        self.ensure_one()

        try:
            # Optionally call API to revoke token
            # oauth_service = self.env['dotykacka.oauth.service']
            # oauth_service.revoke_token(self.config_id, self.access_token)
            pass
        except Exception as e:
            _logger.warning('Failed to revoke token via API: %s', str(e))

        self.write({
            'active': False,
        })

        _logger.info('OAuth token revoked for config %s', self.config_id.cloud_id)

    @api.model
    def create(self, vals):
        """When creating a new token, deactivate old tokens for the same config."""
        if 'config_id' in vals:
            # Deactivate old tokens
            old_tokens = self.search([
                ('config_id', '=', vals['config_id']),
                ('active', '=', True),
            ])
            old_tokens.write({'active': False})

            # Update config to point to new token
            config = self.env['dotykacka.config'].browse(vals['config_id'])

        record = super().create(vals)

        # Update config to point to new token
        if record.config_id:
            record.config_id.write({'oauth_id': record.id})

        return record

    @api.model
    def cleanup_old_tokens(self):
        """
        Cleanup old inactive tokens.

        This is meant to be called by a cron job to remove old tokens.
        Keeps tokens from the last 30 days.
        """
        cutoff_date = datetime.now() - timedelta(days=30)
        old_tokens = self.search([
            ('active', '=', False),
            ('create_date', '<', cutoff_date),
        ])

        count = len(old_tokens)
        old_tokens.unlink()

        _logger.info('Cleaned up %d old OAuth tokens', count)
        return count

    def action_refresh(self):
        """Action to manually refresh token from UI."""
        self.ensure_one()
        try:
            self.refresh_access_token()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Token refreshed successfully!'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            raise ValidationError(_('Failed to refresh token: %s') % str(e))

    def action_revoke(self):
        """Action to manually revoke token from UI."""
        self.ensure_one()
        self.revoke_token()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Token revoked successfully!'),
                'type': 'success',
                'sticky': False,
            }
        }
