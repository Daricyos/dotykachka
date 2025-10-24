{
    'name': 'Dotykacka Import',
    'summary': 'Import orders, customers, products, invoices and payments from Dotykacka POS to Odoo',
    'description': '''
        One-way integration Dotykacka → Odoo

        Features:
        - Webhook-based real-time synchronization
        - OAuth 2.0 authentication with Dotypos API v2
        - Import customers, products, orders, invoices, and payments
        - Handle order updates and deletions
        - Cron fallback for missed webhooks
        - Rate limit handling (150 req/30 min)
        - Filter orders by status (on-site only, skip takeaway)
        - Multiple payment methods support
    ''',
    'author': 'GymBeam',
    'license': 'AGPL-3',
    'website': 'https://www.gymbeam.com',
    'category': 'Sales',
    'version': '18.0.1.0.0',
    'depends': [
        'base',
        'sale',
        'account',
        'product',
        'api_manager',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',
        # Data
        'data/api_provider.xml',
        'data/api_requests.xml',
        'data/ir_cron.xml',
        'data/payment_method_mapping.xml',
        # Views
        'views/dotykacka_config_views.xml',
        'views/dotykacka_sync_log_views.xml',
        'views/dotykacka_webhook_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/res_partner_views.xml',
        'views/product_views.xml',
        'views/menu_items.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
