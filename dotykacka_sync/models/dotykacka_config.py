"""Dotykačka Configuration Model."""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DotykackaConfig(models.Model):
    """Dotykačka Integration Configuration."""

    _name = 'dotykacka.config'
    _description = 'Dotykačka Configuration'
    _rec_name = 'cloud_id'

    # Basic Configuration
    cloud_id = fields.Char(
        string='Cloud ID',
        required=True,
        help='Your Dotykačka Cloud ID (from Dotypos API)'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )

    # OAuth Configuration
    client_id = fields.Char(
        string='Client ID',
        required=True,
        help='OAuth Client ID from Dotykačka'
    )
    client_secret = fields.Char(
        string='Client Secret',
        required=True,
        help='OAuth Client Secret from Dotykačka'
    )
    redirect_uri = fields.Char(
        string='Redirect URI',
        help='OAuth redirect URI (must match Dotykačka app settings)'
    )

    # Current OAuth Token
    oauth_id = fields.Many2one(
        'dotykacka.oauth',
        string='Current OAuth Token',
        readonly=True
    )
    is_authenticated = fields.Boolean(
        string='Is Authenticated',
        compute='_compute_is_authenticated',
        store=True
    )

    # API Configuration
    api_base_url = fields.Char(
        string='API Base URL',
        default='https://api.dotypos.com',
        required=True,
        help='Dotypos API base URL'
    )
    api_provider_id = fields.Many2one(
        'api_manager.provider',
        string='API Provider',
        help='API Manager provider for Dotykačka',
        readonly=True
    )

    # Webhook Configuration
    webhook_url = fields.Char(
        string='Webhook URL',
        compute='_compute_webhook_url',
        store=False,
        help='URL where Dotykačka will send webhook events'
    )
    webhook_id = fields.Char(
        string='Registered Webhook ID',
        readonly=True,
        help='ID of registered webhook in Dotykačka'
    )
    webhook_active = fields.Boolean(
        string='Webhook Active',
        default=False,
        readonly=True
    )

    # Sync Settings
    sync_customers = fields.Boolean(
        string='Sync Customers',
        default=True,
        help='Enable customer synchronization'
    )
    sync_products = fields.Boolean(
        string='Sync Products',
        default=True,
        help='Enable product synchronization'
    )
    sync_orders = fields.Boolean(
        string='Sync Orders',
        default=True,
        help='Enable order synchronization'
    )
    order_status_filter = fields.Selection(
        [
            ('on_site', 'On Site Only'),
            ('all', 'All Statuses'),
        ],
        string='Order Status Filter',
        default='on_site',
        required=True,
        help='Filter orders by status. "On Site Only" ignores takeaway orders (handled in KeyCRM)'
    )

    # Default Settings
    default_salesperson_id = fields.Many2one(
        'res.users',
        string='Default Salesperson',
        help='Default salesperson for orders when not mapped from Dotykačka'
    )
    default_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Default Warehouse',
        help='Default warehouse for orders'
    )
    default_pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Default Pricelist',
        help='Default pricelist for orders'
    )

    # Rate Limiting
    rate_limit_requests = fields.Integer(
        string='Rate Limit (requests)',
        default=150,
        help='Maximum requests per rate limit period'
    )
    rate_limit_period = fields.Integer(
        string='Rate Limit Period (seconds)',
        default=1800,  # 30 minutes
        help='Rate limit time window in seconds'
    )

    # Sync Status
    last_sync_date = fields.Datetime(
        string='Last Sync',
        readonly=True
    )
    last_sync_status = fields.Selection(
        [
            ('success', 'Success'),
            ('partial', 'Partial'),
            ('failed', 'Failed'),
        ],
        string='Last Sync Status',
        readonly=True
    )
    sync_error_count = fields.Integer(
        string='Sync Error Count',
        default=0,
        readonly=True
    )

    # State
    active = fields.Boolean(
        string='Active',
        default=True
    )

    _sql_constraints = [
        ('cloud_id_company_uniq', 'unique(cloud_id, company_id)',
         'Cloud ID must be unique per company!'),
    ]

    @api.depends('oauth_id', 'oauth_id.is_valid')
    def _compute_is_authenticated(self):
        """Check if we have a valid OAuth token."""
        for record in self:
            record.is_authenticated = bool(
                record.oauth_id and record.oauth_id.is_valid
            )

    @api.depends('cloud_id')
    def _compute_webhook_url(self):
        """Compute webhook URL based on current instance."""
        for record in self:
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            record.webhook_url = f"{base_url}/dotykacka/webhook/{record.cloud_id}"

    def action_authorize_oauth(self):
        """Open OAuth authorization wizard or redirect to authorization URL."""
        self.ensure_one()
        # This will be implemented in oauth_service
        return {
            'type': 'ir.actions.act_url',
            'url': self._get_oauth_authorization_url(),
            'target': 'new',
        }

    def _get_oauth_authorization_url(self):
        """Get OAuth authorization URL."""
        self.ensure_one()
        # Construct OAuth authorization URL
        auth_url = f"{self.api_base_url}/oauth/authorize"
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri or self.webhook_url,
            'response_type': 'code',
            'scope': 'openid profile email',  # Adjust scopes as needed
        }
        from urllib.parse import urlencode
        return f"{auth_url}?{urlencode(params)}"

    def action_refresh_token(self):
        """Manually refresh OAuth token."""
        self.ensure_one()
        if not self.oauth_id:
            raise ValidationError(_('No OAuth token found. Please authorize first.'))
        self.oauth_id.refresh_access_token()

    def action_register_webhook(self):
        """Register webhook with Dotykačka."""
        self.ensure_one()
        if not self.is_authenticated:
            raise ValidationError(_('Please authenticate with Dotykačka first.'))

        # This will be implemented in dotykacka_api service
        api_client = self.env['dotykacka.api'].create_client(self)
        webhook_id = api_client.register_webhook(self.webhook_url)

        self.write({
            'webhook_id': webhook_id,
            'webhook_active': True,
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Webhook registered successfully!'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_unregister_webhook(self):
        """Unregister webhook from Dotykačka."""
        self.ensure_one()
        if not self.webhook_id:
            raise ValidationError(_('No webhook registered.'))

        # This will be implemented in dotykacka_api service
        api_client = self.env['dotykacka.api'].create_client(self)
        api_client.unregister_webhook(self.webhook_id)

        self.write({
            'webhook_id': False,
            'webhook_active': False,
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Webhook unregistered successfully!'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_test_connection(self):
        """Test connection to Dotykačka API."""
        self.ensure_one()
        if not self.is_authenticated:
            raise ValidationError(_('Please authenticate with Dotykačka first.'))

        try:
            # This will be implemented in dotykacka_api service
            api_client = self.env['dotykacka.api'].create_client(self)
            result = api_client.test_connection()

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Connection successful! Cloud: %s') % result.get('name', 'Unknown'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            raise ValidationError(_('Connection failed: %s') % str(e))

    def action_sync_now(self):
        """Trigger manual synchronization."""
        self.ensure_one()
        if not self.is_authenticated:
            raise ValidationError(_('Please authenticate with Dotykačka first.'))

        # This will trigger the sync process
        self.env['dotykacka.sync.service'].sync_all(self)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Synchronization started!'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_view_sync_logs(self):
        """View sync logs for this configuration."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sync Logs'),
            'res_model': 'dotykacka.sync.log',
            'view_mode': 'tree,form',
            'domain': [('config_id', '=', self.id)],
            'context': {'default_config_id': self.id},
        }

    @api.model
    def create(self, vals):
        """Create API provider when config is created."""
        record = super().create(vals)
        record._create_api_provider()
        return record

    def _create_api_provider(self):
        """Create or update API Manager provider for this configuration."""
        self.ensure_one()

        provider_vals = {
            'name': f'Dotykačka - {self.cloud_id}',
            'internal_reference': f'dotykacka_{self.cloud_id}',
            'server_domain': self.api_base_url.replace('https://', '').replace('http://', ''),
            'server_scheme': 'https',
            'authentication_method': 'bearer_token',
            'dynamic_token': True,
            'rel_companies': [(6, 0, [self.company_id.id])],
        }

        if self.api_provider_id:
            self.api_provider_id.write(provider_vals)
        else:
            provider = self.env['api_manager.provider'].create(provider_vals)
            self.api_provider_id = provider.id
