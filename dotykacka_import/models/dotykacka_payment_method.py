"""Dotykacka Payment Method Mapping."""

import logging
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DotykackaPaymentMethod(models.Model):
    """Map Dotykacka payment methods to Odoo journals."""

    _name = 'dotykacka.payment.method'
    _description = 'Dotykacka Payment Method Mapping'
    _rec_name = 'dotykacka_method'

    config_id = fields.Many2one(
        'dotykacka.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
    )
    dotykacka_method = fields.Selection(
        [
            ('CASH', 'Cash'),
            ('CARD', 'Payment Card'),
            ('CHECK', 'Check'),
            ('VOUCHER', 'Food/Meal Voucher'),
            ('BANK_TRANSFER', 'Bank Transfer'),
            ('ELECTRONIC_VOUCHER', 'Electronic Food/Meal Voucher'),
            ('COUPON', 'Voucher/Coupon'),
            ('QERKO', 'QERKO'),
            ('CORRENCY', 'Currency'),
            ('GLOVO', 'Glovo'),
            ('WOLT', 'Wolt'),
            ('BOLT', 'Bolt Food'),
            ('UBER_EATS', 'Uber Eats'),
        ],
        string='Dotykacka Payment Method',
        required=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        required=True,
        domain="[('type', 'in', ['cash', 'bank']), ('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='config_id.company_id',
        store=True,
    )
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        (
            'method_config_unique',
            'unique(dotykacka_method, config_id)',
            'Payment method must be unique per configuration!',
        ),
    ]

    @api.constrains('journal_id', 'config_id')
    def _check_journal_company(self):
        """Ensure journal belongs to the same company as config."""
        for record in self:
            if record.journal_id.company_id != record.config_id.company_id:
                raise ValidationError(
                    _('Journal must belong to the same company as the configuration.')
                )

    def name_get(self):
        """Override name display."""
        result = []
        for record in self:
            method_name = dict(self._fields['dotykacka_method'].selection).get(record.dotykacka_method)
            name = f"{method_name} → {record.journal_id.name}"
            result.append((record.id, name))
        return result
