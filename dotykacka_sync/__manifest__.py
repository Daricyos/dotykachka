{
    'name': 'Dotykačka Sync',
    'version': '18.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'One-way synchronization from Dotykačka POS to Odoo',
    'description': """
        Dotykačka to Odoo Synchronization
        ==================================

        This module implements a one-way integration from Dotykačka POS to Odoo 18:

        Features:
        ---------
        * Event-driven synchronization via webhooks
        * Cron-based fallback for missed events
        * OAuth 2.0 authentication with token refresh
        * Customer synchronization (res.partner)
        * Product synchronization (product.product)
        * Sales Order creation and updates (sale.order)
        * Automatic invoice generation (account.move)
        * Payment synchronization and reconciliation (account.payment)
        * Order deletion handling (cancel orders, invoices, payments)
        * Payment method mapping to Odoo journals
        * Status-based filtering (only 'on site' orders)
        * API rate limit handling

        Technical:
        ----------
        * Based on Dotykačka API v2
        * Extends api_manager module
        * RESTful webhook endpoints
        * Comprehensive logging
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'sale_management',
        'account',
        'product',
        'api_manager',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',

        # Data
        'data/payment_method_data.xml',
        'data/cron.xml',

        # Views
        'views/dotykacka_config_views.xml',
        'views/dotykacka_sync_log_views.xml',
        'views/dotykacka_menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
