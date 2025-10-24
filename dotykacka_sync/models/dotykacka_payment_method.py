from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class DotykackaPaymentMethod(models.Model):
    """Mapping between Dotykačka payment methods and Odoo journals."""

    _name = 'dotykacka.payment.method'
    _description = 'Dotykačka Payment Method Mapping'
    _rec_name = 'dotykacka_method_name'

    config_id = fields.Many2one(
        'dotykacka.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
    )

    # Dotykačka payment method details
    dotykacka_method_id = fields.Char(
        string='Dotykačka Method ID',
        required=True,
        help='Payment method ID from Dotykačka',
    )

    dotykacka_method_name = fields.Char(
        string='Dotykačka Method Name',
        required=True,
        help='Payment method name from Dotykačka (e.g., Cash, Card, Voucher)',
    )

    dotykacka_method_type = fields.Selection(
        [
            ('cash', 'Cash'),
            ('card', 'Card'),
            ('voucher', 'Voucher'),
            ('credit', 'Credit'),
            ('online', 'Online Payment'),
            ('glovo', 'Glovo'),
            ('wolt', 'Wolt'),
            ('other', 'Other'),
        ],
        string='Payment Type',
        required=True,
        default='other',
        help='Type of payment method',
    )

    # Odoo journal mapping
    journal_id = fields.Many2one(
        'account.journal',
        string='Odoo Journal',
        required=True,
        domain="[('type', 'in', ['cash', 'bank'])]",
        help='Journal to use for this payment method in Odoo',
    )

    # Additional settings
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Enable/disable this payment method mapping',
    )

    force_payment_account = fields.Many2one(
        'account.account',
        string='Force Payment Account',
        help='Override default payment account from journal',
    )

    notes = fields.Text(
        string='Notes',
        help='Additional notes about this payment method',
    )

    _sql_constraints = [
        (
            'dotykacka_method_config_uniq',
            'unique(dotykacka_method_id, config_id)',
            'Payment method mapping must be unique per configuration!',
        ),
    ]

    @api.constrains('journal_id', 'config_id')
    def _check_journal_company(self):
        """Ensure journal belongs to the same company as configuration."""
        for record in self:
            if record.journal_id.company_id != record.config_id.company_id:
                raise ValidationError(
                    _('Journal company must match configuration company.')
                )

    def get_journal_for_payment(self, dotykacka_method_id, config_id):
        """
        Get Odoo journal for a Dotykačka payment method.

        Args:
            dotykacka_method_id (str): Dotykačka payment method ID
            config_id (int): Configuration ID

        Returns:
            account.journal: Odoo journal record or None
        """
        mapping = self.search([
            ('dotykacka_method_id', '=', dotykacka_method_id),
            ('config_id', '=', config_id),
            ('active', '=', True),
        ], limit=1)

        return mapping.journal_id if mapping else None

    @api.model
    def create_default_mappings(self, config_id):
        """
        Create default payment method mappings for a configuration.

        Args:
            config_id (int): Configuration ID
        """
        config = self.env['dotykacka.config'].browse(config_id)

        # Get or create default journals
        cash_journal = self.env['account.journal'].search([
            ('type', '=', 'cash'),
            ('company_id', '=', config.company_id.id),
        ], limit=1)

        bank_journal = self.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', config.company_id.id),
        ], limit=1)

        # Default payment method mappings
        default_methods = [
            {
                'dotykacka_method_id': '1',
                'dotykacka_method_name': 'Cash',
                'dotykacka_method_type': 'cash',
                'journal_id': cash_journal.id if cash_journal else False,
            },
            {
                'dotykacka_method_id': '2',
                'dotykacka_method_name': 'Card',
                'dotykacka_method_type': 'card',
                'journal_id': bank_journal.id if bank_journal else False,
            },
            {
                'dotykacka_method_id': '3',
                'dotykacka_method_name': 'Voucher',
                'dotykacka_method_type': 'voucher',
                'journal_id': bank_journal.id if bank_journal else False,
            },
            {
                'dotykacka_method_id': '4',
                'dotykacka_method_name': 'Online Payment',
                'dotykacka_method_type': 'online',
                'journal_id': bank_journal.id if bank_journal else False,
            },
        ]

        for method_data in default_methods:
            if not method_data['journal_id']:
                continue

            # Check if mapping already exists
            existing = self.search([
                ('dotykacka_method_id', '=', method_data['dotykacka_method_id']),
                ('config_id', '=', config_id),
            ])

            if not existing:
                method_data['config_id'] = config_id
                self.create(method_data)
