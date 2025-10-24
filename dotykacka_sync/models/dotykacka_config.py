from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class DotykackaConfig(models.Model):
    """Configuration for Dotykačka API integration."""

    _name = 'dotykacka.config'
    _description = 'Dotykačka Configuration'
    _rec_name = 'cloud_name'

    # Company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    # Basic Configuration
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Enable/disable this configuration',
    )
    cloud_id = fields.Char(
        string='Cloud ID',
        required=True,
        help='Your Dotykačka Cloud ID',
    )
    cloud_name = fields.Char(
        string='Cloud Name',
        help='Descriptive name for this cloud',
    )
    branch_id = fields.Char(
        string='Branch ID',
        help='Default branch ID for operations',
    )

    # OAuth Configuration
    client_id = fields.Char(
        string='Client ID',
        required=True,
        help='OAuth Client ID from Dotykačka',
    )
    client_secret = fields.Char(
        string='Client Secret',
        required=True,
        help='OAuth Client Secret from Dotykačka',
    )
    redirect_uri = fields.Char(
        string='Redirect URI',
        help='OAuth redirect URI (if needed)',
    )

    # Tokens (managed automatically)
    access_token = fields.Char(
        string='Access Token',
        readonly=True,
        help='Current OAuth access token',
    )
    refresh_token = fields.Char(
        string='Refresh Token',
        readonly=True,
        help='OAuth refresh token',
    )
    token_expires_at = fields.Datetime(
        string='Token Expires At',
        readonly=True,
        help='When the access token expires',
    )

    # API Configuration
    api_base_url = fields.Char(
        string='API Base URL',
        default='https://api.dotykacka.cz',
        required=True,
        help='Base URL for Dotykačka API',
    )
    api_version = fields.Selection(
        [('v2', 'API v2')],
        string='API Version',
        default='v2',
        required=True,
    )

    # Webhook Configuration
    webhook_enabled = fields.Boolean(
        string='Enable Webhooks',
        default=True,
        help='Enable webhook-based synchronization',
    )
    webhook_url = fields.Char(
        string='Webhook URL',
        compute='_compute_webhook_url',
        help='URL for Dotykačka to send webhooks',
    )
    webhook_secret = fields.Char(
        string='Webhook Secret',
        help='Secret for webhook validation',
    )

    # Sync Settings
    sync_customers = fields.Boolean(
        string='Sync Customers',
        default=True,
        help='Synchronize customer data',
    )
    sync_products = fields.Boolean(
        string='Sync Products',
        default=True,
        help='Synchronize product data',
    )
    sync_orders = fields.Boolean(
        string='Sync Orders',
        default=True,
        help='Synchronize sales orders',
    )
    auto_create_invoice = fields.Boolean(
        string='Auto Create Invoices',
        default=True,
        help='Automatically create invoices for orders',
    )
    auto_validate_invoice = fields.Boolean(
        string='Auto Validate Invoices',
        default=True,
        help='Automatically validate created invoices',
    )
    auto_reconcile_payments = fields.Boolean(
        string='Auto Reconcile Payments',
        default=True,
        help='Automatically reconcile payments to invoices',
    )

    # Order Filters
    order_status_filter = fields.Selection(
        [
            ('all', 'All Orders'),
            ('on_site', 'On Site Only'),
            ('takeaway', 'Takeaway Only'),
        ],
        string='Order Status Filter',
        default='on_site',
        required=True,
        help='Which order types to import',
    )

    # Sync Frequency (for cron fallback)
    sync_interval = fields.Integer(
        string='Sync Interval (minutes)',
        default=15,
        help='How often to run fallback sync (in minutes)',
    )
    last_sync_date = fields.Datetime(
        string='Last Sync Date',
        readonly=True,
        help='Last successful synchronization',
    )

    # Payment Method Mapping
    payment_method_ids = fields.One2many(
        'dotykacka.payment.method',
        'config_id',
        string='Payment Methods',
    )

    # Statistics
    total_synced_orders = fields.Integer(
        string='Total Synced Orders',
        compute='_compute_statistics',
        store=False,
    )
    total_synced_customers = fields.Integer(
        string='Total Synced Customers',
        compute='_compute_statistics',
        store=False,
    )
    total_synced_products = fields.Integer(
        string='Total Synced Products',
        compute='_compute_statistics',
        store=False,
    )

    # Status
    status = fields.Selection(
        [
            ('draft', 'Draft'),
            ('active', 'Active'),
            ('error', 'Error'),
        ],
        string='Status',
        default='draft',
        help='Configuration status',
    )
    error_message = fields.Text(
        string='Error Message',
        readonly=True,
    )

    _sql_constraints = [
        (
            'cloud_id_company_uniq',
            'unique(cloud_id, company_id)',
            'Cloud ID must be unique per company!',
        ),
    ]

    @api.depends('api_base_url')
    def _compute_webhook_url(self):
        """Compute webhook URL based on Odoo instance."""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            record.webhook_url = f"{base_url}/dotykacka/webhook/{record.id}"

    @api.depends('company_id')
    def _compute_statistics(self):
        """Compute synchronization statistics."""
        for record in self:
            # Count synced orders
            record.total_synced_orders = self.env['sale.order'].search_count([
                ('company_id', '=', record.company_id.id),
                ('dotykacka_order_id', '!=', False),
            ])
            # Count synced customers
            record.total_synced_customers = self.env['res.partner'].search_count([
                ('company_id', '=', record.company_id.id),
                ('dotykacka_customer_id', '!=', False),
            ])
            # Count synced products
            record.total_synced_products = self.env['product.product'].search_count([
                ('dotykacka_product_id', '!=', False),
            ])

    @api.constrains('api_base_url')
    def _check_api_base_url(self):
        """Validate API base URL."""
        for record in self:
            if record.api_base_url and record.api_base_url.endswith('/'):
                raise ValidationError(_('API Base URL should not end with a slash.'))

    def action_test_connection(self):
        """Test API connection and OAuth authentication."""
        self.ensure_one()
        try:
            oauth = self.env['dotykacka.oauth'].create({'config_id': self.id})
            oauth.refresh_access_token()

            # Test a simple API call
            response = oauth.call_api('GET', f'/v2/clouds/{self.cloud_id}/branches')

            if response.get('data'):
                self.write({
                    'status': 'active',
                    'error_message': False,
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Successful'),
                        'message': _('Successfully connected to Dotykačka API.'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('API returned unexpected response.'))

        except Exception as e:
            self.write({
                'status': 'error',
                'error_message': str(e),
            })
            raise UserError(
                _('Connection failed: %s') % str(e)
            )

    def action_register_webhooks(self):
        """Register webhooks with Dotykačka."""
        self.ensure_one()
        oauth = self.env['dotykacka.oauth'].create({'config_id': self.id})

        # Webhook events to register
        events = [
            'order.created',
            'order.updated',
            'order.deleted',
        ]

        for event in events:
            try:
                payload = {
                    'url': self.webhook_url,
                    'event': event,
                    'active': True,
                }
                if self.webhook_secret:
                    payload['secret'] = self.webhook_secret

                response = oauth.call_api(
                    'POST',
                    f'/v2/clouds/{self.cloud_id}/webhooks',
                    data=payload,
                )

                self.env['dotykacka.sync.log'].create({
                    'config_id': self.id,
                    'log_type': 'webhook',
                    'direction': 'outgoing',
                    'endpoint': f'/v2/clouds/{self.cloud_id}/webhooks',
                    'status_code': 200,
                    'request_data': str(payload),
                    'response_data': str(response),
                })

            except Exception as e:
                raise UserError(
                    _('Failed to register webhook for event %s: %s') % (event, str(e))
                )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Webhooks Registered'),
                'message': _('Successfully registered %d webhooks.') % len(events),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_sync_now(self):
        """Manually trigger synchronization."""
        self.ensure_one()

        # Create sync jobs
        sync_log = self.env['dotykacka.sync.log'].create({
            'config_id': self.id,
            'log_type': 'sync',
            'direction': 'incoming',
            'endpoint': 'manual_sync',
        })

        try:
            # Sync customers
            if self.sync_customers:
                customer_sync = self.env['dotykacka.customer.sync'].create({
                    'config_id': self.id,
                })
                customer_sync.sync_all_customers()

            # Sync products
            if self.sync_products:
                product_sync = self.env['dotykacka.product.sync'].create({
                    'config_id': self.id,
                })
                product_sync.sync_all_products()

            # Sync orders
            if self.sync_orders:
                order_sync = self.env['dotykacka.order.sync'].create({
                    'config_id': self.id,
                })
                order_sync.sync_recent_orders()

            self.last_sync_date = fields.Datetime.now()
            sync_log.write({
                'status_code': 200,
                'response_data': 'Manual sync completed successfully',
            })

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Complete'),
                    'message': _('Manual synchronization completed successfully.'),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            sync_log.write({
                'status_code': 500,
                'error_message': str(e),
            })
            raise UserError(
                _('Synchronization failed: %s') % str(e)
            )

    @api.model
    def cron_sync_all_configs(self):
        """Cron job to sync all active configurations."""
        configs = self.search([
            ('active', '=', True),
            ('status', '=', 'active'),
        ])

        for config in configs:
            try:
                config.action_sync_now()
            except Exception as e:
                config.write({
                    'status': 'error',
                    'error_message': str(e),
                })
