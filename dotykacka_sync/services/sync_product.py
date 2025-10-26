"""Product Synchronization Service."""

import logging

from odoo import _, api, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DotykackaProductSync(models.AbstractModel):
    """Service for synchronizing products from Dotykačka to Odoo."""

    _name = 'dotykacka.sync.product'
    _description = 'Dotykačka Product Sync Service'

    @api.model
    def sync_products(self, config, limit=100):
        """
        Sync products from Dotykačka to Odoo.

        Args:
            config: dotykacka.config record
            limit: Maximum number of products to sync per batch

        Returns:
            dict: Sync statistics
        """
        if not config.sync_products:
            _logger.info('Product sync is disabled for config %s', config.cloud_id)
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
                # Fetch products from API
                response = api_client.get_products(limit=limit, offset=offset)
                products = response.get('data', [])

                if not products:
                    break

                for product_data in products:
                    try:
                        result = self._sync_product(config, product_data)
                        stats[result] += 1
                    except Exception as e:
                        _logger.error('Error syncing product %s: %s', product_data.get('id'), str(e))
                        stats['errors'] += 1

                        # Log error
                        self.env['dotykacka.sync.log'].log_error(
                            config=config,
                            sync_type='product',
                            sync_action='update',
                            message=f"Failed to sync product {product_data.get('id')}",
                            error=e,
                            dotykacka_id=str(product_data.get('id')),
                            response_data=str(product_data)
                        )

                # Check if there are more products
                if len(products) < limit:
                    break

                offset += limit

            _logger.info('Product sync completed: %s', stats)
            return stats

        except Exception as e:
            _logger.error('Product sync failed: %s', str(e))
            raise

    def _sync_product(self, config, product_data):
        """
        Sync single product.

        Args:
            config: dotykacka.config record
            product_data: Product data from Dotykačka API

        Returns:
            str: 'created', 'updated', or 'skipped'
        """
        product_id = product_data.get('id')
        if not product_id:
            return 'skipped'

        # Skip if product is not sellable
        if not product_data.get('sellable', True):
            return 'skipped'

        # Check if product already exists by Dotykačka ID
        product = self.env['product.product'].search([
            ('dotykacka_product_id', '=', str(product_id))
        ], limit=1)

        # If not found by ID, try to find by SKU or barcode
        if not product:
            sku = product_data.get('sku')
            barcode = product_data.get('barcode')

            if sku:
                product = self.env['product.product'].search([
                    ('default_code', '=', sku)
                ], limit=1)

            if not product and barcode:
                product = self.env['product.product'].search([
                    ('barcode', '=', barcode)
                ], limit=1)

        # Prepare product values
        vals = self._prepare_product_vals(product_data)

        if product:
            # Update existing product
            product.write(vals)
            action = 'updated'
        else:
            # Create new product
            product = self.env['product.product'].create(vals)
            action = 'created'

        # Log success
        self.env['dotykacka.sync.log'].log_success(
            config=config,
            sync_type='product',
            sync_action=action,
            message=f"Product {product.name} synced successfully",
            dotykacka_id=str(product_id),
            odoo_model='product.product',
            odoo_id=product.id,
            odoo_record_name=product.name
        )

        return action

    def _prepare_product_vals(self, product_data):
        """
        Prepare Odoo product values from Dotykačka product data.

        Args:
            product_data: Product data from API

        Returns:
            dict: Product values for create/write
        """
        vals = {
            'dotykacka_product_id': str(product_data.get('id')),
            'dotykacka_sync_date': self.env.cr.now(),
        }

        # Name (required)
        vals['name'] = product_data.get('name') or f"Product {product_data.get('id')}"

        # SKU / Internal Reference
        if product_data.get('sku'):
            vals['default_code'] = product_data['sku']
            vals['dotykacka_sku'] = product_data['sku']

        # Barcode
        if product_data.get('barcode'):
            vals['barcode'] = product_data['barcode']

        # Description
        if product_data.get('description'):
            vals['description_sale'] = product_data['description']

        # Pricing
        if product_data.get('priceWithVat') is not None:
            vals['list_price'] = float(product_data['priceWithVat'])

        if product_data.get('priceWithoutVat') is not None:
            vals['standard_price'] = float(product_data['priceWithoutVat'])

        # Product type
        vals['type'] = 'consu'  # Consumable by default

        # Can be sold
        vals['sale_ok'] = product_data.get('sellable', True)

        # Can be purchased
        vals['purchase_ok'] = False  # Usually POS products are not purchased through Odoo

        # Tax
        if product_data.get('vat') is not None:
            vat_rate = float(product_data['vat'])
            # Try to find matching tax
            tax = self.env['account.tax'].search([
                ('type_tax_use', '=', 'sale'),
                ('amount', '=', vat_rate),
                ('company_id', '=', self.env.company.id),
            ], limit=1)
            if tax:
                vals['taxes_id'] = [(6, 0, [tax.id])]

        # Category
        if product_data.get('categoryId'):
            # Could map categories if needed
            pass

        # Unit of measure
        if product_data.get('unit'):
            uom = self._get_or_create_uom(product_data['unit'])
            if uom:
                vals['uom_id'] = uom.id
                vals['uom_po_id'] = uom.id

        return vals

    def _get_or_create_uom(self, unit_name):
        """
        Get or create unit of measure.

        Args:
            unit_name: Unit name from Dotykačka

        Returns:
            uom.uom: Unit of measure record
        """
        # Try to find existing UoM
        uom = self.env['uom.uom'].search([
            ('name', '=ilike', unit_name)
        ], limit=1)

        if not uom:
            # Try common mappings
            mapping = {
                'kg': 'kg',
                'g': 'g',
                'l': 'L',
                'ml': 'mL',
                'pcs': 'Units',
                'piece': 'Units',
                'unit': 'Units',
            }

            mapped_name = mapping.get(unit_name.lower())
            if mapped_name:
                uom = self.env['uom.uom'].search([
                    ('name', '=', mapped_name)
                ], limit=1)

        return uom

    @api.model
    def sync_product_by_id(self, config, product_id):
        """
        Sync single product by ID.

        Args:
            config: dotykacka.config record
            product_id: Product ID in Dotykačka

        Returns:
            product.product: Synced product record
        """
        api_client = self.env['dotykacka.api'].create_client(config)

        try:
            product_data = api_client.get_product(product_id)
            self._sync_product(config, product_data)

            return self.env['product.product'].search([
                ('dotykacka_product_id', '=', str(product_id))
            ], limit=1)

        except Exception as e:
            _logger.error('Failed to sync product %s: %s', product_id, str(e))
            raise ValidationError(_(
                'Failed to sync product: %s'
            ) % str(e))
