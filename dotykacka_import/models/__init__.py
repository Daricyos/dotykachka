"""Import models."""

from . import dotykacka_config
from . import dotykacka_oauth
from . import dotykacka_webhook
from . import dotykacka_importer
from . import dotykacka_sync_log
from . import dotykacka_payment_method
from . import sale_order
from . import account_move
from . import account_payment
from . import res_partner
from . import product_product

__all__ = [
    'dotykacka_config',
    'dotykacka_oauth',
    'dotykacka_webhook',
    'dotykacka_importer',
    'dotykacka_sync_log',
    'dotykacka_payment_method',
    'sale_order',
    'account_move',
    'account_payment',
    'res_partner',
    'product_product',
]
