"""Dotykacka Webhook Management."""

import logging
from odoo import _, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DotykackaWebhook(models.Model):
    """Manage Dotykacka Webhooks."""

    _name = 'dotykacka.webhook'
    _description = 'Dotykacka Webhook'
    _inherit = ['mail.thread']

    config_id = fields.Many2one(
        'dotykacka.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    name = fields.Char(
        string='Webhook Name',
        compute='_compute_name',
        store=True,
    )
    webhook_id = fields.Char(
        string='Webhook ID',
        readonly=True,
        help='ID returned by Dotykacka API',
        tracking=True,
    )
    event_type = fields.Selection(
        [
            ('order', 'Order Events'),
            ('customer', 'Customer Events'),
            ('product', 'Product Events'),
        ],
        string='Event Type',
        required=True,
        tracking=True,
    )
    url = fields.Char(
        string='Webhook URL',
        required=True,
        tracking=True,
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
    )
    registered = fields.Boolean(
        string='Registered',
        default=False,
        readonly=True,
        tracking=True,
    )
    registered_date = fields.Datetime(
        string='Registered Date',
        readonly=True,
    )
    last_triggered = fields.Datetime(
        string='Last Triggered',
        readonly=True,
    )
    trigger_count = fields.Integer(
        string='Trigger Count',
        default=0,
        readonly=True,
    )

    def _compute_name(self):
        """Compute webhook name."""
        for webhook in self:
            webhook.name = f"{webhook.event_type} - {webhook.config_id.name}"

    def action_register(self):
        """Register webhook in Dotykacka."""
        self.ensure_one()

        if self.registered:
            raise ValidationError(_('Webhook is already registered.'))

        config = self.config_id
        oauth = self.env['dotykacka.oauth']
        access_token = oauth.ensure_valid_token(config)

        # Get API request for webhook registration
        request = self.env['api_manager.request'].search([
            ('name', '=', 'Register Webhook'),
            ('provider', '=', config.api_provider_id.id),
        ], limit=1)

        if not request:
            raise ValidationError(_('API request for webhook registration not found.'))

        # Prepare webhook data
        webhook_data = {
            'url': self.url,
            'events': self._get_event_names(),
            'active': self.active,
        }

        # Send request
        response = request.send_request(
            params={'{cloud_id}': config.cloud_id},
            data=webhook_data,
            headers={'Authorization': f'Bearer {access_token}'},
            return_type='decoded',
        )

        if response and response.get('id'):
            self.write({
                'webhook_id': response['id'],
                'registered': True,
                'registered_date': fields.Datetime.now(),
            })
            _logger.info(f"Webhook registered successfully: {self.name}")
        else:
            raise ValidationError(_('Failed to register webhook.'))

    def action_unregister(self):
        """Unregister webhook from Dotykacka."""
        self.ensure_one()

        if not self.registered or not self.webhook_id:
            return

        config = self.config_id
        oauth = self.env['dotykacka.oauth']
        access_token = oauth.ensure_valid_token(config)

        # Get API request for webhook deletion
        request = self.env['api_manager.request'].search([
            ('name', '=', 'Delete Webhook'),
            ('provider', '=', config.api_provider_id.id),
        ], limit=1)

        if not request:
            _logger.warning('API request for webhook deletion not found.')
            return

        # Send delete request
        request.send_request(
            params={
                '{cloud_id}': config.cloud_id,
                '{webhook_id}': self.webhook_id,
            },
            headers={'Authorization': f'Bearer {access_token}'},
            return_type='status_code',
        )

        self.write({
            'webhook_id': False,
            'registered': False,
        })
        _logger.info(f"Webhook unregistered: {self.name}")

    def action_test(self):
        """Test webhook by triggering a test event."""
        self.ensure_one()

        if not self.registered:
            raise ValidationError(_('Webhook must be registered before testing.'))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Test Webhook'),
                'message': _('Please trigger an event in Dotykacka to test the webhook.'),
                'type': 'info',
                'sticky': True,
            }
        }

    def _get_event_names(self):
        """Get event names based on event type."""
        event_mapping = {
            'order': ['order.created', 'order.updated', 'order.deleted'],
            'customer': ['customer.created', 'customer.updated'],
            'product': ['product.created', 'product.updated'],
        }
        return event_mapping.get(self.event_type, [])

    def increment_trigger_count(self):
        """Increment trigger count and update last triggered time."""
        self.ensure_one()
        self.write({
            'trigger_count': self.trigger_count + 1,
            'last_triggered': fields.Datetime.now(),
        })
