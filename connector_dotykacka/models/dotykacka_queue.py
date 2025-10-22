"""Module for logging Dotykacka PoS orders."""
__version__ = "1.0"

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DotykackaQueue(models.Model):
    """Queue processor for incoming dotykacka data."""

    _name = 'dotykacka.queue'
    _order = 'write_date desc'

    order_external_id = fields.Char()
    order_related_id = fields.Char()
    request_data = fields.Text(required=True)

    @api.constrains('order_external_id', 'order_related_id')
    def _check_external_fields(self):
        for record in self:
            if not (record.order_external_id or record.order_related_id):
                raise ValidationError(
                    _("Either Order External ID or Order Related ID must be provided.")
                )
