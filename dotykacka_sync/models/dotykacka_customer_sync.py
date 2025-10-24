from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DotykackaCustomerSync(models.TransientModel):
    """Customer synchronization from Dotykačka to Odoo."""

    _name = 'dotykacka.customer.sync'
    _description = 'Dotykačka Customer Synchronization'

    config_id = fields.Many2one(
        'dotykacka.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
    )

    def _get_oauth(self):
        """Get OAuth handler for API calls."""
        return self.env['dotykacka.oauth'].create({'config_id': self.config_id.id})

    def sync_customer(self, customer_data):
        """
        Sync a single customer from Dotykačka to Odoo.

        Args:
            customer_data (dict): Customer data from Dotykačka API

        Returns:
            res.partner: Odoo partner record
        """
        self.ensure_one()

        dotykacka_id = str(customer_data.get('id'))
        if not dotykacka_id:
            _logger.warning('Customer data missing ID: %s', customer_data)
            return None

        # Check if customer already exists
        partner = self.env['res.partner'].search([
            ('dotykacka_customer_id', '=', dotykacka_id),
            ('company_id', '=', self.config_id.company_id.id),
        ], limit=1)

        # Prepare partner values
        partner_vals = self._prepare_partner_vals(customer_data)

        try:
            if partner:
                # Update existing partner
                partner.write(partner_vals)
                _logger.info('Updated customer %s (Dotykačka ID: %s)', partner.name, dotykacka_id)
            else:
                # Create new partner
                partner_vals['dotykacka_customer_id'] = dotykacka_id
                partner_vals['company_id'] = self.config_id.company_id.id
                partner = self.env['res.partner'].create(partner_vals)
                _logger.info('Created customer %s (Dotykačka ID: %s)', partner.name, dotykacka_id)

            # Log success
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'sync',
                'direction': 'incoming',
                'endpoint': 'customer_sync',
                'status_code': 200,
                'customer_id': partner.id,
                'response_data': f'Customer {partner.name} synced successfully',
            })

            return partner

        except Exception as e:
            _logger.error('Failed to sync customer %s: %s', dotykacka_id, str(e))

            # Log error
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'error',
                'direction': 'incoming',
                'endpoint': 'customer_sync',
                'status_code': 0,
                'error_message': str(e),
                'request_data': str(customer_data),
            })

            raise

    def _prepare_partner_vals(self, customer_data):
        """
        Prepare partner values from Dotykačka customer data.

        Args:
            customer_data (dict): Customer data from Dotykačka

        Returns:
            dict: Partner values for create/write
        """
        vals = {}

        # Name (required)
        first_name = customer_data.get('firstName', '')
        last_name = customer_data.get('lastName', '')
        company_name = customer_data.get('companyName', '')

        if company_name:
            vals['name'] = company_name
            vals['is_company'] = True
            # If company, first/last names are contact person
            if first_name or last_name:
                vals['contact_name'] = f"{first_name} {last_name}".strip()
        else:
            vals['name'] = f"{first_name} {last_name}".strip() or 'Unknown Customer'
            vals['is_company'] = False

        # Contact information
        if customer_data.get('email'):
            vals['email'] = customer_data['email']

        if customer_data.get('phone'):
            vals['phone'] = customer_data['phone']

        if customer_data.get('mobile'):
            vals['mobile'] = customer_data['mobile']

        # Address information
        street_parts = []
        if customer_data.get('streetName'):
            street_parts.append(customer_data['streetName'])
        if customer_data.get('streetNumber'):
            street_parts.append(customer_data['streetNumber'])

        if street_parts:
            vals['street'] = ' '.join(street_parts)

        if customer_data.get('city'):
            vals['city'] = customer_data['city']

        if customer_data.get('zip'):
            vals['zip'] = customer_data['zip']

        # Country
        if customer_data.get('countryCode'):
            country = self.env['res.country'].search([
                ('code', '=', customer_data['countryCode'].upper())
            ], limit=1)
            if country:
                vals['country_id'] = country.id

        # Tax ID / VAT
        if customer_data.get('taxId'):
            vals['vat'] = customer_data['taxId']

        if customer_data.get('companyId'):
            vals['company_registry'] = customer_data['companyId']

        # Customer flag
        vals['customer_rank'] = 1  # Mark as customer

        # Additional fields
        if customer_data.get('note'):
            vals['comment'] = customer_data['note']

        if customer_data.get('barcode'):
            vals['barcode'] = customer_data['barcode']

        # Dotykačka specific
        if customer_data.get('displayName'):
            vals['dotykacka_display_name'] = customer_data['displayName']

        return vals

    def sync_all_customers(self, limit=None):
        """
        Sync all customers from Dotykačka to Odoo.

        Args:
            limit (int): Optional limit on number of customers to sync
        """
        self.ensure_one()

        if not self.config_id.sync_customers:
            _logger.info('Customer sync is disabled for config %s', self.config_id.cloud_name)
            return

        oauth = self._get_oauth()
        endpoint = f'/v2/clouds/{self.config_id.cloud_id}/customers'

        try:
            synced_count = 0
            error_count = 0

            # Fetch customers using pagination
            for customer_data in oauth.call_api_paginated('GET', endpoint):
                try:
                    self.sync_customer(customer_data)
                    synced_count += 1

                    if limit and synced_count >= limit:
                        break

                except Exception as e:
                    error_count += 1
                    _logger.error('Failed to sync customer: %s', str(e))
                    continue

            _logger.info(
                'Customer sync completed: %d synced, %d errors',
                synced_count, error_count
            )

            return {
                'synced': synced_count,
                'errors': error_count,
            }

        except Exception as e:
            _logger.error('Customer sync failed: %s', str(e))
            raise UserError(_('Customer synchronization failed: %s') % str(e))

    def sync_customer_by_id(self, dotykacka_customer_id):
        """
        Sync a specific customer by Dotykačka ID.

        Args:
            dotykacka_customer_id (str): Dotykačka customer ID

        Returns:
            res.partner: Synced partner record
        """
        self.ensure_one()
        oauth = self._get_oauth()
        endpoint = f'/v2/clouds/{self.config_id.cloud_id}/customers/{dotykacka_customer_id}'

        try:
            customer_data = oauth.call_api('GET', endpoint)
            if customer_data:
                return self.sync_customer(customer_data)
            else:
                raise UserError(_('Customer not found in Dotykačka'))

        except Exception as e:
            _logger.error('Failed to sync customer %s: %s', dotykacka_customer_id, str(e))
            raise UserError(_('Failed to sync customer: %s') % str(e))
