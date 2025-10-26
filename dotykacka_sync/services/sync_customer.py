"""Customer Synchronization Service."""

import logging

from odoo import _, api, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DotykackaCustomerSync(models.AbstractModel):
    """Service for synchronizing customers from Dotykačka to Odoo."""

    _name = 'dotykacka.sync.customer'
    _description = 'Dotykačka Customer Sync Service'

    @api.model
    def sync_customers(self, config, limit=100):
        """
        Sync customers from Dotykačka to Odoo.

        Args:
            config: dotykacka.config record
            limit: Maximum number of customers to sync

        Returns:
            dict: Sync statistics
        """
        if not config.sync_customers:
            _logger.info('Customer sync is disabled for config %s', config.cloud_id)
            return {'skipped': True}

        api_client = self.env['dotykacka.api'].create_client(config)
        stats = {
            'created': 0,
            'updated': 0,
            'errors': 0,
            'skipped': 0,
        }

        try:
            offset = 0
            while True:
                # Fetch customers from API
                response = api_client.get_customers(limit=limit, offset=offset)
                customers = response.get('data', [])

                if not customers:
                    break

                for customer_data in customers:
                    try:
                        result = self._sync_customer(config, customer_data)
                        stats[result] += 1
                    except Exception as e:
                        _logger.error('Error syncing customer %s: %s', customer_data.get('id'), str(e))
                        stats['errors'] += 1

                        # Log error
                        self.env['dotykacka.sync.log'].log_error(
                            config=config,
                            sync_type='customer',
                            sync_action='update',
                            message=f"Failed to sync customer {customer_data.get('id')}",
                            error=e,
                            dotykacka_id=str(customer_data.get('id')),
                            response_data=str(customer_data)
                        )

                # Check if there are more customers
                if len(customers) < limit:
                    break

                offset += limit

            _logger.info('Customer sync completed: %s', stats)
            return stats

        except Exception as e:
            _logger.error('Customer sync failed: %s', str(e))
            raise

    def _sync_customer(self, config, customer_data):
        """
        Sync single customer.

        Args:
            config: dotykacka.config record
            customer_data: Customer data from Dotykačka API

        Returns:
            str: 'created', 'updated', or 'skipped'
        """
        customer_id = customer_data.get('id')
        if not customer_id:
            return 'skipped'

        # Check if customer already exists
        partner = self.env['res.partner'].search([
            ('dotykacka_customer_id', '=', str(customer_id))
        ], limit=1)

        # Prepare partner values
        vals = self._prepare_partner_vals(customer_data)

        if partner:
            # Update existing partner
            partner.write(vals)
            action = 'updated'
        else:
            # Create new partner
            partner = self.env['res.partner'].create(vals)
            action = 'created'

        # Log success
        self.env['dotykacka.sync.log'].log_success(
            config=config,
            sync_type='customer',
            sync_action=action,
            message=f"Customer {partner.name} synced successfully",
            dotykacka_id=str(customer_id),
            odoo_model='res.partner',
            odoo_id=partner.id,
            odoo_record_name=partner.name
        )

        return action

    def _prepare_partner_vals(self, customer_data):
        """
        Prepare Odoo partner values from Dotykačka customer data.

        Args:
            customer_data: Customer data from API

        Returns:
            dict: Partner values for create/write
        """
        vals = {
            'dotykacka_customer_id': str(customer_data.get('id')),
            'dotykacka_sync_date': self.env.cr.now(),
            'customer_rank': 1,  # Mark as customer
        }

        # Name (required)
        first_name = customer_data.get('firstName', '')
        last_name = customer_data.get('lastName', '')
        company_name = customer_data.get('companyName', '')

        if company_name:
            vals['name'] = company_name
            vals['is_company'] = True
            if first_name or last_name:
                vals['child_ids'] = [(0, 0, {
                    'name': f"{first_name} {last_name}".strip(),
                    'type': 'contact',
                })]
        else:
            vals['name'] = f"{first_name} {last_name}".strip() or f"Customer {customer_data.get('id')}"
            vals['is_company'] = False

        # Contact information
        if customer_data.get('email'):
            vals['email'] = customer_data['email']

        if customer_data.get('phone'):
            vals['phone'] = customer_data['phone']

        if customer_data.get('mobile'):
            vals['mobile'] = customer_data['mobile']

        # Address
        street_parts = []
        if customer_data.get('street'):
            street_parts.append(customer_data['street'])
        if customer_data.get('houseNumber'):
            street_parts.append(customer_data['houseNumber'])

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

        if customer_data.get('registrationId'):
            vals['company_registry'] = customer_data['registrationId']

        # Additional notes
        if customer_data.get('note'):
            vals['comment'] = customer_data['note']

        return vals

    @api.model
    def sync_customer_by_id(self, config, customer_id):
        """
        Sync single customer by ID.

        Args:
            config: dotykacka.config record
            customer_id: Customer ID in Dotykačka

        Returns:
            res.partner: Synced partner record
        """
        api_client = self.env['dotykacka.api'].create_client(config)

        try:
            customer_data = api_client.get_customer(customer_id)
            self._sync_customer(config, customer_data)

            return self.env['res.partner'].search([
                ('dotykacka_customer_id', '=', str(customer_id))
            ], limit=1)

        except Exception as e:
            _logger.error('Failed to sync customer %s: %s', customer_id, str(e))
            raise ValidationError(_(
                'Failed to sync customer: %s'
            ) % str(e))
