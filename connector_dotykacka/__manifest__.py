# pylama:ignore=C0114,D100
{
    'name': 'Dotykacka Connector',
    'summary': (
        'This module provides necessary functionality for synchronization with Dotykacka API.'
    ),
    'author': 'GymBeam',
    'license': 'AGPL-3',
    'website': 'https://www.gymbeam.com',
    'category': 'API',
    'version': '18.0.0.1.0',
    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'product',
        'stock',
        'point_of_sale',
        'api_manager',
    ],
    # always loaded
    'data': [
        # Data
        'data/providers.xml',
        'data/requests.xml',
        # Security
        'security/ir.model.access.csv',
        # Views
        'views/product.xml',
        'views/pos_order.xml',
        'views/pos_config_views.xml',
        'views/pos_payment_method_views.xml',
        'views/dotykacka_order.xml',
        'views/dotykacka_queue.xml',
        'views/actions.xml',
        'views/menu_items.xml',
    ],
    # only loaded in demonstration mode
    'demo': [],
    'installable': True,
    # 'post_load': 'patch_json_request',
}
