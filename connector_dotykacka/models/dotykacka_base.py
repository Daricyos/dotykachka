"""Module for Dotykacka Base."""
__version__ = "1.1"

import logging

from dateutil.parser import parse
from dateutil.tz import UTC
from odoo import models
from odoo.addons.api_manager.utils import exceptions

_logger = logging.getLogger(__name__)


class DotykackaBase(models.TransientModel):
    """Base model for dotykacka functionality."""

    _name = 'dotykacka.base'

    def dotykacka_map_data(self, model, recordset):
        """Dynamic method to get dataset."""
        return self.env[model].dotykacka_get_dataset(recordset)

    def write_metadata(self, record, data: dict, company):
        """
        Write metadata to product.product.

        :param record: object
        :param data: dict - response from dotykacka
        :param company: company object
        """
        self.env.company = company
        if isinstance(data, dict):
            if 'id' in data.keys():
                if not record:
                    record = record.browse(int(data.get('externalId', False)))
                record.with_context(dotykacka_noupdate=True).write(
                    {
                        'dotykacka_id': data['id'],
                        'dotykacka_exported': True,
                        'dotykacka_last_update': self.convert_timestamp(data['versionDate']),
                        'dotykacka_created_at': self.convert_timestamp(data['created']),
                    }
                )

    @staticmethod
    def convert_timestamp(timestamp):
        """Convert json timestamp to naive (UTC) datetime object."""
        date_time = parse(timestamp)
        result = date_time.astimezone(UTC).replace(tzinfo=None)
        return result

    def ping_pos_hw(self, cloud_id, branch_id):
        """
        Ping dotykacka HW before sending request.

        :param cloud_id: ID of cloud
        :param branch_id: ID of branch
        :return: bool
        """
        request_pos = self.env.ref('connector_dotykacka.api_request_dotykacka_pos_actions')

        data = {"action": "order/hello"}
        response = request_pos.send_request_dotykacka(
            params={"{cloud_id}": cloud_id, "{branch_id}": branch_id},
            data=data,
            return_type='decoded',
        )
        return bool(response)

    def _renew_token(self):
        """Renew token if expired."""
        request_name = 'connector_dotykacka.api_request_dotykacka_refresh_token'
        provider_name = 'connector_dotykacka.provider_dotykacka'
        request = self.env.ref(request_name)
        provider = self.env.ref(provider_name)
        cloud_id = self.env['api_manager.request_parameter'].search(
            [
                ('provider', '=', provider.id),
                ('key', '=', 'cloud_id'),
                ('company_id', '=', self.env.company.id),
            ]
        )
        data_payload = {
            "_cloudId": cloud_id.value,
        }
        result = request.send_request(data=data_payload)
        if not result:
            raise exceptions.InvalidResponse(request_name, request.response)
        response_data = request.decode_response()
        if 'accessToken' in response_data.keys():
            company_related_token = self.env['api_manager.request_parameter'].search(
                [
                    ('provider', '=', provider.id),
                    ('key', '=', 'token'),
                    ('company_id', '=', self.env.company.id),
                ]
            )
            if company_related_token:
                company_related_token.value = response_data['accessToken']
            else:
                provider.token = response_data['accessToken']
        else:
            _logger.error(f"Unable to get accessToken. Response: {response_data}")
