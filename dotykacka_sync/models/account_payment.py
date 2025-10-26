"""Extend account.payment for Dotykačka integration."""

from odoo import fields, models


class AccountPayment(models.Model):
    """Extend Payment to track Dotykačka payment."""

    _inherit = 'account.payment'

    dotykacka_payment_id = fields.Char(
        string='Dotykačka Payment ID',
        help='Payment ID from Dotykačka POS',
        copy=False,
        index=True
    )
    dotykacka_receipt_id = fields.Char(
        string='Dotykačka Receipt ID',
        help='Receipt/Order ID from Dotykačka POS',
        copy=False,
        index=True
    )
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
        help='Payment method from Dotykačka POS',
        copy=False
    )
    dotykacka_sync_date = fields.Datetime(
        string='Dotykačka Last Sync',
        help='When this payment was last synced from Dotykačka',
        readonly=True,
        copy=False
    )
    dotykacka_config_id = fields.Many2one(
        'dotykacka.config',
        string='Dotykačka Configuration',
        help='Dotykačka configuration used for this payment',
        ondelete='restrict',
        copy=False
    )
