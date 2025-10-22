"""Module for Dotykacka API Request extension."""
__version__ = "1.0"

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class APIRequest(models.Model):  # pylint:disable=too-few-public-methods
    """Extension of api_manager.request with dotykacka customization."""

    _inherit = 'api_manager.request'

    def send_request_dotykacka(self, **kwargs):
        """Try to send request with access token renewal in case of fail."""
        attempt = kwargs.get("retry", 1)
        max_tries = kwargs.get("max_tries", 2)
        if attempt > max_tries:
            return {}
        data = self.send_request(**kwargs)
        if isinstance(data, dict) and {'error', 'reason'} <= data.keys():
            if (
                data['error'] == 'Forbidden'
                and data['reason'] == 'ACCESS_TOKEN_EXPIRED'
                or data['reason'] == 'INVALID_ACCESS_TOKEN'
            ):
                self.env['dotykacka.base']._renew_token()  # pylint:disable=W0212
                self.clear()
                data = self.send_request_dotykacka(**dict(kwargs, retry=attempt + 1))
        return data
