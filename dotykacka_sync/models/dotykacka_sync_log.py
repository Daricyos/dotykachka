"""Dotykačka Synchronization Log."""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class DotykackaSyncLog(models.Model):
    """Log all synchronization operations."""

    _name = 'dotykacka.sync.log'
    _description = 'Dotykačka Sync Log'
    _order = 'create_date desc'
    _rec_name = 'sync_type'

    config_id = fields.Many2one(
        'dotykacka.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
        index=True
    )
    company_id = fields.Many2one(
        related='config_id.company_id',
        string='Company',
        store=True,
        readonly=True,
        index=True
    )

    # Sync Information
    sync_type = fields.Selection(
        [
            ('customer', 'Customer'),
            ('product', 'Product'),
            ('order', 'Order'),
            ('invoice', 'Invoice'),
            ('payment', 'Payment'),
            ('webhook', 'Webhook Event'),
            ('cron', 'Cron Sync'),
            ('manual', 'Manual Sync'),
        ],
        string='Sync Type',
        required=True,
        index=True
    )
    sync_action = fields.Selection(
        [
            ('create', 'Create'),
            ('update', 'Update'),
            ('delete', 'Delete'),
            ('skip', 'Skip'),
        ],
        string='Action',
        required=True
    )
    sync_status = fields.Selection(
        [
            ('success', 'Success'),
            ('warning', 'Warning'),
            ('error', 'Error'),
        ],
        string='Status',
        required=True,
        default='success',
        index=True
    )

    # External Reference
    dotykacka_id = fields.Char(
        string='Dotykačka ID',
        help='External ID from Dotykačka',
        index=True
    )
    dotykacka_type = fields.Char(
        string='Dotykačka Type',
        help='Type of entity in Dotykačka (e.g., receipt, order, customer)'
    )

    # Odoo Reference
    odoo_model = fields.Char(
        string='Odoo Model',
        help='Odoo model name (e.g., sale.order, res.partner)'
    )
    odoo_id = fields.Integer(
        string='Odoo Record ID',
        help='ID of created/updated Odoo record'
    )
    odoo_record_name = fields.Char(
        string='Odoo Record Name',
        help='Name of Odoo record for display'
    )

    # Log Details
    message = fields.Text(
        string='Message',
        help='Descriptive message about the sync operation'
    )
    error_message = fields.Text(
        string='Error Message',
        help='Error message if sync failed'
    )
    error_traceback = fields.Text(
        string='Error Traceback',
        help='Full error traceback for debugging'
    )

    # Request/Response Data
    request_data = fields.Text(
        string='Request Data',
        help='API request data (JSON)'
    )
    response_data = fields.Text(
        string='Response Data',
        help='API response data (JSON)'
    )
    webhook_payload = fields.Text(
        string='Webhook Payload',
        help='Webhook payload received from Dotykačka'
    )

    # Performance
    duration_ms = fields.Integer(
        string='Duration (ms)',
        help='Time taken for sync operation in milliseconds'
    )

    # Metadata
    triggered_by = fields.Selection(
        [
            ('webhook', 'Webhook'),
            ('cron', 'Cron Job'),
            ('manual', 'Manual'),
            ('api', 'API Call'),
        ],
        string='Triggered By',
        default='manual'
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        default=lambda self: self.env.user,
        help='User who triggered the sync (if manual)'
    )

    def action_view_record(self):
        """Open the related Odoo record."""
        self.ensure_one()
        if not self.odoo_model or not self.odoo_id:
            return

        return {
            'type': 'ir.actions.act_window',
            'res_model': self.odoo_model,
            'res_id': self.odoo_id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_retry_sync(self):
        """Retry failed sync operation."""
        self.ensure_one()
        if self.sync_status != 'error':
            return

        # This will be implemented based on sync_type
        if self.sync_type == 'customer':
            return self.env['dotykacka.sync.customer'].retry_sync(self)
        elif self.sync_type == 'product':
            return self.env['dotykacka.sync.product'].retry_sync(self)
        elif self.sync_type == 'order':
            return self.env['dotykacka.sync.order'].retry_sync(self)

    @api.model
    def create_log(self, vals):
        """
        Helper method to create log entries with consistent structure.

        Args:
            vals (dict): Log values

        Returns:
            dotykacka.sync.log: Created log record
        """
        return self.create(vals)

    @api.model
    def log_success(self, config, sync_type, sync_action, message, **kwargs):
        """Log successful sync operation."""
        vals = {
            'config_id': config.id,
            'sync_type': sync_type,
            'sync_action': sync_action,
            'sync_status': 'success',
            'message': message,
            'triggered_by': kwargs.get('triggered_by', 'manual'),
        }
        vals.update(kwargs)
        return self.create_log(vals)

    @api.model
    def log_warning(self, config, sync_type, sync_action, message, **kwargs):
        """Log sync operation with warning."""
        vals = {
            'config_id': config.id,
            'sync_type': sync_type,
            'sync_action': sync_action,
            'sync_status': 'warning',
            'message': message,
            'triggered_by': kwargs.get('triggered_by', 'manual'),
        }
        vals.update(kwargs)
        return self.create_log(vals)

    @api.model
    def log_error(self, config, sync_type, sync_action, message, error=None, **kwargs):
        """Log failed sync operation."""
        import traceback

        vals = {
            'config_id': config.id,
            'sync_type': sync_type,
            'sync_action': sync_action,
            'sync_status': 'error',
            'message': message,
            'triggered_by': kwargs.get('triggered_by', 'manual'),
        }

        if error:
            vals['error_message'] = str(error)
            if hasattr(error, '__traceback__'):
                vals['error_traceback'] = ''.join(
                    traceback.format_exception(type(error), error, error.__traceback__)
                )

        vals.update(kwargs)
        return self.create_log(vals)

    @api.model
    def cleanup_old_logs(self, days=90):
        """
        Cleanup old log entries.

        Args:
            days (int): Keep logs from last N days

        Returns:
            int: Number of logs deleted
        """
        from datetime import datetime, timedelta

        cutoff_date = datetime.now() - timedelta(days=days)
        old_logs = self.search([
            ('create_date', '<', cutoff_date),
            ('sync_status', '!=', 'error'),  # Keep error logs longer
        ])

        count = len(old_logs)
        old_logs.unlink()

        _logger.info('Cleaned up %d old sync logs (older than %d days)', count, days)
        return count

    @api.model
    def get_sync_statistics(self, config_id, days=7):
        """
        Get sync statistics for dashboard.

        Args:
            config_id (int): Configuration ID
            days (int): Number of days to analyze

        Returns:
            dict: Sync statistics
        """
        from datetime import datetime, timedelta

        cutoff_date = datetime.now() - timedelta(days=days)

        domain = [
            ('config_id', '=', config_id),
            ('create_date', '>=', cutoff_date),
        ]

        total = self.search_count(domain)
        success = self.search_count(domain + [('sync_status', '=', 'success')])
        warnings = self.search_count(domain + [('sync_status', '=', 'warning')])
        errors = self.search_count(domain + [('sync_status', '=', 'error')])

        by_type = {}
        for sync_type in ['customer', 'product', 'order', 'invoice', 'payment']:
            by_type[sync_type] = self.search_count(domain + [('sync_type', '=', sync_type)])

        return {
            'total': total,
            'success': success,
            'warnings': warnings,
            'errors': errors,
            'success_rate': (success / total * 100) if total > 0 else 0,
            'by_type': by_type,
            'period_days': days,
        }
