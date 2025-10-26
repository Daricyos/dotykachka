"""Dotykačka Payment Method Mapping."""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DotykackaPaymentMapping(models.Model):
    """Map Dotykačka payment methods to Odoo journals."""

    _name = 'dotykacka.payment.mapping'
    _description = 'Dotykačka Payment Method Mapping'
    _order = 'sequence, dotykacka_payment_method'

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

    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Order of payment methods in lists'
    )

    # Dotykačka Payment Method
    dotykacka_payment_method = fields.Selection(
        [
            ('cash', 'Cash'),
            ('card', 'Card'),
            ('voucher', 'Voucher'),
            ('credit_note', 'Credit Note'),
            ('mobile_payment', 'Mobile Payment'),
            ('wolt', 'Wolt'),
            ('glovo', 'Glovo'),
            ('foodora', 'Foodora'),
            ('uber_eats', 'Uber Eats'),
            ('other', 'Other'),
        ],
        string='Dotykačka Payment Method',
        required=True,
        help='Payment method from Dotykačka API'
    )
    dotykacka_payment_id = fields.Char(
        string='Dotykačka Payment ID',
        help='External payment method ID from Dotykačka (if applicable)'
    )
    payment_method_name = fields.Char(
        string='Payment Method Name',
        help='Custom name for this payment method'
    )

    # Odoo Journal Mapping
    journal_id = fields.Many2one(
        'account.journal',
        string='Payment Journal',
        required=True,
        domain="[('type', 'in', ['cash', 'bank']), ('company_id', '=', company_id)]",
        help='Odoo journal to use for this payment method'
    )
    payment_method_line_id = fields.Many2one(
        'account.payment.method.line',
        string='Payment Method',
        domain="[('journal_id', '=', journal_id)]",
        help='Specific payment method within the journal'
    )

    # Additional Settings
    is_default = fields.Boolean(
        string='Default',
        help='Use this mapping when payment method is not specified'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Disable this mapping to stop using it'
    )

    # Statistics
    payment_count = fields.Integer(
        string='Payment Count',
        compute='_compute_payment_count',
        help='Number of payments using this mapping'
    )

    _sql_constraints = [
        ('dotykacka_method_config_uniq',
         'unique(dotykacka_payment_method, config_id, dotykacka_payment_id)',
         'Payment method mapping must be unique per configuration!'),
    ]

    @api.depends('journal_id')
    def _compute_payment_count(self):
        """Compute number of payments using this mapping."""
        for record in self:
            # This will be implemented when payments are created
            record.payment_count = 0

    @api.constrains('is_default')
    def _check_single_default(self):
        """Ensure only one default mapping per configuration."""
        for record in self:
            if record.is_default:
                other_defaults = self.search([
                    ('config_id', '=', record.config_id.id),
                    ('is_default', '=', True),
                    ('id', '!=', record.id),
                ])
                if other_defaults:
                    raise ValidationError(_(
                        'Only one payment mapping can be set as default per configuration.'
                    ))

    @api.onchange('dotykacka_payment_method')
    def _onchange_dotykacka_payment_method(self):
        """Set suggested journal based on payment method."""
        if not self.journal_id and self.dotykacka_payment_method:
            # Try to find appropriate journal
            journal = False

            if self.dotykacka_payment_method == 'cash':
                journal = self.env['account.journal'].search([
                    ('type', '=', 'cash'),
                    ('company_id', '=', self.company_id.id),
                ], limit=1)
            elif self.dotykacka_payment_method in ['card', 'mobile_payment']:
                journal = self.env['account.journal'].search([
                    ('type', '=', 'bank'),
                    ('company_id', '=', self.company_id.id),
                    ('name', 'ilike', 'bank'),
                ], limit=1)

            if journal:
                self.journal_id = journal

    @api.model
    def get_journal_for_payment_method(self, config, payment_method, payment_id=None):
        """
        Get Odoo journal for Dotykačka payment method.

        Args:
            config: dotykacka.config record
            payment_method: Payment method from Dotykačka (str)
            payment_id: Optional external payment ID

        Returns:
            account.journal: Matched journal or False

        Raises:
            ValidationError: If no mapping found and no default
        """
        # Try exact match with payment ID
        if payment_id:
            mapping = self.search([
                ('config_id', '=', config.id),
                ('dotykacka_payment_method', '=', payment_method),
                ('dotykacka_payment_id', '=', payment_id),
                ('active', '=', True),
            ], limit=1)
            if mapping:
                return mapping.journal_id

        # Try match by payment method only
        mapping = self.search([
            ('config_id', '=', config.id),
            ('dotykacka_payment_method', '=', payment_method),
            ('active', '=', True),
        ], limit=1)
        if mapping:
            return mapping.journal_id

        # Try default mapping
        default_mapping = self.search([
            ('config_id', '=', config.id),
            ('is_default', '=', True),
            ('active', '=', True),
        ], limit=1)
        if default_mapping:
            return default_mapping.journal_id

        raise ValidationError(_(
            'No payment mapping found for method "%s" and no default mapping configured.\n'
            'Please configure payment method mappings in Dotykačka settings.'
        ) % payment_method)

    @api.model
    def get_payment_method_line(self, config, payment_method, journal, payment_id=None):
        """
        Get payment method line for journal.

        Args:
            config: dotykacka.config record
            payment_method: Payment method from Dotykačka (str)
            journal: account.journal record
            payment_id: Optional external payment ID

        Returns:
            account.payment.method.line: Payment method line or False
        """
        # Try to get from mapping
        mapping = self.search([
            ('config_id', '=', config.id),
            ('dotykacka_payment_method', '=', payment_method),
            ('journal_id', '=', journal.id),
            ('active', '=', True),
        ], limit=1)

        if mapping and mapping.payment_method_line_id:
            return mapping.payment_method_line_id

        # Get first available inbound payment method for journal
        payment_method_line = self.env['account.payment.method.line'].search([
            ('journal_id', '=', journal.id),
            ('payment_type', '=', 'inbound'),
        ], limit=1)

        return payment_method_line

    @api.model
    def create_default_mappings(self, config):
        """
        Create default payment method mappings for a configuration.

        Args:
            config: dotykacka.config record

        Returns:
            dotykacka.payment.mapping: Created mappings
        """
        # Get default journals
        cash_journal = self.env['account.journal'].search([
            ('type', '=', 'cash'),
            ('company_id', '=', config.company_id.id),
        ], limit=1)

        bank_journal = self.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', config.company_id.id),
        ], limit=1)

        if not cash_journal or not bank_journal:
            raise ValidationError(_(
                'Cannot create default mappings: No cash or bank journal found for company %s'
            ) % config.company_id.name)

        mappings = []

        # Cash mapping (default)
        mappings.append(self.create({
            'config_id': config.id,
            'dotykacka_payment_method': 'cash',
            'journal_id': cash_journal.id,
            'is_default': True,
            'sequence': 1,
        }))

        # Card mapping
        mappings.append(self.create({
            'config_id': config.id,
            'dotykacka_payment_method': 'card',
            'journal_id': bank_journal.id,
            'sequence': 2,
        }))

        # Mobile payment mapping
        mappings.append(self.create({
            'config_id': config.id,
            'dotykacka_payment_method': 'mobile_payment',
            'journal_id': bank_journal.id,
            'sequence': 3,
        }))

        # Delivery services
        for seq, method in enumerate(['wolt', 'glovo', 'foodora', 'uber_eats'], start=4):
            mappings.append(self.create({
                'config_id': config.id,
                'dotykacka_payment_method': method,
                'journal_id': bank_journal.id,
                'sequence': seq,
            }))

        return self.browse([m.id for m in mappings])

    def action_view_payments(self):
        """View payments using this mapping."""
        self.ensure_one()
        # This will be implemented when payment sync is done
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payments'),
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            'domain': [
                ('journal_id', '=', self.journal_id.id),
                ('dotykacka_payment_method', '=', self.dotykacka_payment_method),
            ],
        }
