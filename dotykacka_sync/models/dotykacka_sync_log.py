from odoo import models, fields, api, _


class DotykackaSyncLog(models.Model):
    """Log for Dotykačka synchronization operations."""

    _name = 'dotykacka.sync.log'
    _description = 'Dotykačka Sync Log'
    _order = 'create_date desc'
    _rec_name = 'create_date'

    config_id = fields.Many2one(
        'dotykacka.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
        index=True,
    )

    log_type = fields.Selection(
        [
            ('auth', 'Authentication'),
            ('api', 'API Call'),
            ('webhook', 'Webhook'),
            ('sync', 'Synchronization'),
            ('error', 'Error'),
            ('warning', 'Warning'),
        ],
        string='Log Type',
        required=True,
        index=True,
    )

    direction = fields.Selection(
        [
            ('incoming', 'Incoming'),
            ('outgoing', 'Outgoing'),
        ],
        string='Direction',
        required=True,
    )

    endpoint = fields.Char(
        string='Endpoint',
        help='API endpoint or webhook path',
    )

    status_code = fields.Integer(
        string='Status Code',
        help='HTTP status code',
    )

    request_data = fields.Text(
        string='Request Data',
        help='Request payload or webhook data',
    )

    response_data = fields.Text(
        string='Response Data',
        help='Response from API or webhook',
    )

    error_message = fields.Text(
        string='Error Message',
        help='Error details if request failed',
    )

    # Relations
    order_id = fields.Many2one(
        'sale.order',
        string='Related Order',
        ondelete='set null',
    )

    customer_id = fields.Many2one(
        'res.partner',
        string='Related Customer',
        ondelete='set null',
    )

    product_id = fields.Many2one(
        'product.product',
        string='Related Product',
        ondelete='set null',
    )

    invoice_id = fields.Many2one(
        'account.move',
        string='Related Invoice',
        ondelete='set null',
    )

    payment_id = fields.Many2one(
        'account.payment',
        string='Related Payment',
        ondelete='set null',
    )

    # Computed fields
    success = fields.Boolean(
        string='Success',
        compute='_compute_success',
        store=True,
    )

    @api.depends('status_code', 'error_message')
    def _compute_success(self):
        """Determine if the log entry represents a successful operation."""
        for record in self:
            if record.error_message:
                record.success = False
            elif record.status_code:
                record.success = 200 <= record.status_code < 300
            else:
                record.success = True

    @api.model
    def cleanup_old_logs(self, days=30):
        """
        Remove logs older than specified days.

        Args:
            days (int): Number of days to keep logs
        """
        cutoff_date = fields.Datetime.now() - timedelta(days=days)
        old_logs = self.search([('create_date', '<', cutoff_date)])
        old_logs.unlink()

    @api.model
    def get_error_summary(self, config_id=None, days=7):
        """
        Get summary of errors for the last N days.

        Args:
            config_id (int): Optional config ID to filter by
            days (int): Number of days to look back

        Returns:
            dict: Error summary statistics
        """
        domain = [
            ('create_date', '>=', fields.Datetime.now() - timedelta(days=days)),
            ('success', '=', False),
        ]

        if config_id:
            domain.append(('config_id', '=', config_id))

        error_logs = self.search(domain)

        return {
            'total_errors': len(error_logs),
            'auth_errors': len(error_logs.filtered(lambda l: l.log_type == 'auth')),
            'api_errors': len(error_logs.filtered(lambda l: l.log_type == 'api')),
            'webhook_errors': len(error_logs.filtered(lambda l: l.log_type == 'webhook')),
            'sync_errors': len(error_logs.filtered(lambda l: l.log_type == 'sync')),
        }


from datetime import timedelta
