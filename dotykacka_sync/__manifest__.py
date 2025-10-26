{
    'name': 'Dotykačka Sync',
    'version': '18.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'One-way integration from Dotykačka POS to Odoo',
    'description': """
Dotykačka POS Integration
=========================

This module provides one-way synchronization from Dotykačka POS to Odoo.

Features:
---------
* Event-driven via webhooks with cron fallback
* OAuth 2.0 authentication with automatic token refresh
* Synchronizes customers, products, orders, invoices, and payments
* Supports multiple payment methods with journal mapping
* Handles order creation, updates, and deletions
* Rate limiting for API calls
* Comprehensive sync logging

Business Rules:
---------------
* Only imports orders with status "on site"
* Ignores orders with status "takeaway" (handled in KeyCRM)
* Deleted orders trigger cancellation of related orders, invoices, and payments

Technical:
----------
* Uses Dotypos API v2
* Webhook-driven synchronization
* Cron-based fallback for missed events
* Respects API rate limits (~150 requests/30 min)
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
        'data/api_provider_data.xml',
        'data/api_requests_data.xml',
        'data/cron_jobs.xml',

        # Views
        'views/dotykacka_config_view.xml',
        'views/dotykacka_oauth_view.xml',
        'views/dotykacka_sync_log_view.xml',
        'views/dotykacka_payment_mapping_view.xml',
        'views/sale_order_view.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
