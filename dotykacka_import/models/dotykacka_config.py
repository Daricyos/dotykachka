"""Dotykacka Configuration."""

import logging
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DotykackaConfig(models.Model):
    """Dotykacka Integration Configuration."""

    _name = 'dotykacka.config'
    _description = 'Dotykacka Configuration'
    _inherit = ['mail.thread']

    name = fields.Char(string='Configuration Name', required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )

    # API Configuration
    cloud_id = fields.Char(string='Cloud ID', required=True, tracking=True)
    api_provider_id = fields.Many2one(
        'api_manager.provider',
        string='API Provider',
        required=True,
        domain="[('internal_reference', '=', 'dotykacka')]",
        tracking=True,
    )

    # OAuth Configuration
    oauth_client_id = fields.Char(string='OAuth Client ID', tracking=True)
    oauth_client_secret = fields.Char(string='OAuth Client Secret', tracking=True)
    oauth_redirect_uri = fields.Char(string='OAuth Redirect URI', tracking=True)
    access_token = fields.Char(string='Access Token', readonly=True)
    refresh_token = fields.Char(string='Refresh Token', readonly=True)
    token_expires_at = fields.Datetime(string='Token Expires At', readonly=True)

    # Webhook Configuration
    webhook_url = fields.Char(
        string='Webhook URL',
        compute='_compute_webhook_url',
        store=True,
        help='URL that Dotykacka will call for events',
    )
    webhook_registered = fields.Boolean(
        string='Webhook Registered',
        default=False,
        readonly=True,
        tracking=True,
    )
    webhook_ids = fields.One2many(
        'dotykacka.webhook',
        'config_id',
        string='Webhooks',
    )

    # Sync Settings
    import_on_site_orders = fields.Boolean(
        string='Import On-Site Orders',
        default=True,
        help='Import orders with status "on site"',
    )
    import_takeaway_orders = fields.Boolean(
        string='Import Takeaway Orders',
        default=False,
        help='Import orders with status "takeaway" (usually handled in KeyCRM)',
    )
    auto_confirm_orders = fields.Boolean(
        string='Auto Confirm Orders',
        default=True,
        help='Automatically confirm sales orders after import',
    )
    auto_create_invoice = fields.Boolean(
        string='Auto Create Invoice',
        default=True,
        help='Automatically create and post invoices',
    )
    auto_register_payment = fields.Boolean(
        string='Auto Register Payment',
        default=True,
        help='Automatically register payments and reconcile',
    )

    # Default Values
    default_pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Default Pricelist',
        help='Pricelist used for imported orders',
    )
    default_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Default Warehouse',
        help='Warehouse used for imported orders',
    )
    default_sales_team_id = fields.Many2one(
        'crm.team',
        string='Default Sales Team',
    )

    # Statistics
    last_sync_date = fields.Datetime(
        string='Last Sync Date',
        readonly=True,
    )
    total_orders_imported = fields.Integer(
        string='Total Orders Imported',
        compute='_compute_statistics',
    )
    total_customers_imported = fields.Integer(
        string='Total Customers Imported',
        compute='_compute_statistics',
    )
    total_products_imported = fields.Integer(
        string='Total Products Imported',
        compute='_compute_statistics',
    )

    _sql_constraints = [
        ('cloud_id_unique', 'unique(cloud_id, company_id)', 'Cloud ID must be unique per company!'),
    ]

    @api.depends('company_id')
    def _compute_webhook_url(self):
        """Compute webhook URL based on base URL."""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for config in self:
            config.webhook_url = f"{base_url}/dotykacka/webhook/{config.id}"

    def _compute_statistics(self):
        """Compute import statistics."""
        for config in self:
            # Count imported orders
            orders = self.env['sale.order'].search_count([
                ('dotykacka_config_id', '=', config.id),
            ])
            config.total_orders_imported = orders

            # Count imported customers
            customers = self.env['res.partner'].search_count([
                ('dotykacka_config_id', '=', config.id),
            ])
            config.total_customers_imported = customers

            # Count imported products
            products = self.env['product.product'].search_count([
                ('dotykacka_config_id', '=', config.id),
            ])
            config.total_products_imported = products

    def action_get_oauth_url(self):
        """Generate OAuth authorization URL."""
        self.ensure_one()
        if not self.oauth_client_id or not self.oauth_redirect_uri:
            raise ValidationError(_('Please configure OAuth Client ID and Redirect URI first.'))

        auth_url = (
            f"https://api.dotykacka.cz/oauth/authorize"
            f"?client_id={self.oauth_client_id}"
            f"&redirect_uri={self.oauth_redirect_uri}"
            f"&response_type=code"
            f"&state={self.id}"
        )

        return {
            'type': 'ir.actions.act_url',
            'url': auth_url,
            'target': 'new',
        }

    def action_refresh_token(self):
        """Refresh OAuth access token."""
        self.ensure_one()
        oauth = self.env['dotykacka.oauth']
        oauth.refresh_access_token(self)

    def action_register_webhooks(self):
        """Register webhooks in Dotykacka."""
        self.ensure_one()
        webhook_model = self.env['dotykacka.webhook']

        # Register webhook for orders
        webhook_model.create({
            'config_id': self.id,
            'event_type': 'order',
            'url': self.webhook_url,
        }).action_register()

        self.webhook_registered = True

    def action_unregister_webhooks(self):
        """Unregister all webhooks."""
        self.ensure_one()
        for webhook in self.webhook_ids:
            webhook.action_unregister()
        self.webhook_registered = False

    def action_test_connection(self):
        """Test connection to Dotykacka API."""
        self.ensure_one()
        try:
            request = self.env['api_manager.request'].search([
                ('name', '=', 'Get Orders'),
                ('provider', '=', self.api_provider_id.id),
            ], limit=1)

            if not request:
                raise ValidationError(_('API request not found. Please install data files.'))

            response = request.send_request(
                params={'{cloud_id}': self.cloud_id},
                args={'limit': '1'},
                return_type='decoded',
            )

            if response:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Connection to Dotykacka API is working!'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise ValidationError(_('Failed to connect to Dotykacka API.'))

        except Exception as e:
            raise ValidationError(_('Connection test failed: %s') % str(e))

    def action_sync_now(self):
        """Trigger manual synchronization."""
        self.ensure_one()
        self.env['dotykacka.importer'].sync_orders(self)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync Started'),
                'message': _('Manual synchronization has been triggered.'),
                'type': 'info',
                'sticky': False,
            }
        }

    def cron_sync_orders(self):
        """Cron job to sync orders from Dotykacka."""
        configs = self.search([('active', '=', True)])
        for config in configs:
            try:
                _logger.info(f"Starting sync for config: {config.name}")
                self.env['dotykacka.importer'].sync_orders(config)
                config.last_sync_date = fields.Datetime.now()
            except Exception as e:
                _logger.error(f"Sync failed for config {config.name}: {str(e)}")

    @api.model
    def get_config_by_cloud_id(self, cloud_id):
        """Get configuration by cloud ID."""
        return self.search([('cloud_id', '=', cloud_id), ('active', '=', True)], limit=1)
