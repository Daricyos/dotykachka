from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DotykackaProductSync(models.TransientModel):
    """Product synchronization from Dotykačka to Odoo."""

    _name = 'dotykacka.product.sync'
    _description = 'Dotykačka Product Synchronization'

    config_id = fields.Many2one(
        'dotykacka.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
    )

    def _get_oauth(self):
        """Get OAuth handler for API calls."""
        return self.env['dotykacka.oauth'].create({'config_id': self.config_id.id})

    def sync_product(self, product_data):
        """
        Sync a single product from Dotykačka to Odoo.

        Args:
            product_data (dict): Product data from Dotykačka API

        Returns:
            product.product: Odoo product record
        """
        self.ensure_one()

        dotykacka_id = str(product_data.get('id'))
        if not dotykacka_id:
            _logger.warning('Product data missing ID: %s', product_data)
            return None

        # Check if product already exists by Dotykačka ID
        product = self.env['product.product'].search([
            ('dotykacka_product_id', '=', dotykacka_id),
        ], limit=1)

        # If not found, try to find by SKU or barcode
        if not product:
            sku = product_data.get('sku') or product_data.get('ean')
            if sku:
                product = self.env['product.product'].search([
                    '|',
                    ('default_code', '=', sku),
                    ('barcode', '=', sku),
                ], limit=1)

        # Prepare product values
        product_vals = self._prepare_product_vals(product_data)

        try:
            if product:
                # Update existing product
                product.write(product_vals)
                _logger.info('Updated product %s (Dotykačka ID: %s)', product.name, dotykacka_id)
            else:
                # Create new product
                product_vals['dotykacka_product_id'] = dotykacka_id
                product = self.env['product.product'].create(product_vals)
                _logger.info('Created product %s (Dotykačka ID: %s)', product.name, dotykacka_id)

            # Log success
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'sync',
                'direction': 'incoming',
                'endpoint': 'product_sync',
                'status_code': 200,
                'product_id': product.id,
                'response_data': f'Product {product.name} synced successfully',
            })

            return product

        except Exception as e:
            _logger.error('Failed to sync product %s: %s', dotykacka_id, str(e))

            # Log error
            self.env['dotykacka.sync.log'].create({
                'config_id': self.config_id.id,
                'log_type': 'error',
                'direction': 'incoming',
                'endpoint': 'product_sync',
                'status_code': 0,
                'error_message': str(e),
                'request_data': str(product_data),
            })

            raise

    def _prepare_product_vals(self, product_data):
        """
        Prepare product values from Dotykačka product data.

        Args:
            product_data (dict): Product data from Dotykačka

        Returns:
            dict: Product values for create/write
        """
        vals = {}

        # Name (required)
        vals['name'] = product_data.get('name') or 'Unknown Product'

        # SKU / Internal Reference
        if product_data.get('sku'):
            vals['default_code'] = product_data['sku']

        # Barcode / EAN
        if product_data.get('ean'):
            vals['barcode'] = product_data['ean']
        elif product_data.get('barcode'):
            vals['barcode'] = product_data['barcode']

        # Pricing
        if product_data.get('priceWithVat'):
            vals['list_price'] = float(product_data['priceWithVat'])
        elif product_data.get('sellingPrice'):
            vals['list_price'] = float(product_data['sellingPrice'])

        if product_data.get('priceWithoutVat'):
            # Store price without VAT for reference
            vals['standard_price'] = float(product_data['priceWithoutVat'])

        # Tax handling
        if product_data.get('vatRate'):
            vat_rate = float(product_data['vatRate'])
            # Find matching tax in Odoo
            tax = self._find_or_create_tax(vat_rate)
            if tax:
                vals['taxes_id'] = [(6, 0, [tax.id])]

        # Product type
        vals['type'] = 'consu'  # Consumable by default
        if product_data.get('stockTracking'):
            vals['type'] = 'product'  # Storable if stock tracking enabled

        # Category
        if product_data.get('category'):
            category = self._find_or_create_category(product_data['category'])
            if category:
                vals['categ_id'] = category.id

        # Description
        if product_data.get('description'):
            vals['description'] = product_data['description']

        if product_data.get('note'):
            vals['description_sale'] = product_data['note']

        # Sale/Purchase flags
        vals['sale_ok'] = True
        vals['purchase_ok'] = False  # Typically POS products are not purchased

        # Unit of Measure
        if product_data.get('unit'):
            uom = self._find_uom(product_data['unit'])
            if uom:
                vals['uom_id'] = uom.id
                vals['uom_po_id'] = uom.id

        # Additional fields
        if product_data.get('onStock') is not None:
            vals['qty_available'] = float(product_data['onStock'])

        # Dotykačka specific fields
        if product_data.get('display'):
            vals['dotykacka_display'] = product_data['display']

        if product_data.get('deleted'):
            vals['active'] = not product_data['deleted']

        return vals

    def _find_or_create_tax(self, vat_rate):
        """
        Find or create a tax with the given VAT rate.

        Args:
            vat_rate (float): VAT rate percentage

        Returns:
            account.tax: Tax record
        """
        # Search for existing tax
        tax = self.env['account.tax'].search([
            ('amount', '=', vat_rate),
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', self.config_id.company_id.id),
        ], limit=1)

        if not tax:
            # Create new tax
            tax = self.env['account.tax'].create({
                'name': f'VAT {vat_rate}%',
                'amount': vat_rate,
                'type_tax_use': 'sale',
                'company_id': self.config_id.company_id.id,
            })
            _logger.info('Created tax: VAT %s%%', vat_rate)

        return tax

    def _find_or_create_category(self, category_name):
        """
        Find or create a product category.

        Args:
            category_name (str): Category name

        Returns:
            product.category: Category record
        """
        # Search for existing category
        category = self.env['product.category'].search([
            ('name', '=', category_name),
        ], limit=1)

        if not category:
            # Create new category
            category = self.env['product.category'].create({
                'name': category_name,
            })
            _logger.info('Created category: %s', category_name)

        return category

    def _find_uom(self, unit_name):
        """
        Find unit of measure by name.

        Args:
            unit_name (str): Unit name

        Returns:
            uom.uom: UoM record
        """
        # Try to find by name
        uom = self.env['uom.uom'].search([
            ('name', 'ilike', unit_name),
        ], limit=1)

        return uom

    def sync_all_products(self, limit=None):
        """
        Sync all products from Dotykačka to Odoo.

        Args:
            limit (int): Optional limit on number of products to sync
        """
        self.ensure_one()

        if not self.config_id.sync_products:
            _logger.info('Product sync is disabled for config %s', self.config_id.cloud_name)
            return

        oauth = self._get_oauth()
        endpoint = f'/v2/clouds/{self.config_id.cloud_id}/products'

        try:
            synced_count = 0
            error_count = 0

            # Fetch products using pagination
            for product_data in oauth.call_api_paginated('GET', endpoint):
                try:
                    # Skip deleted products
                    if product_data.get('deleted'):
                        continue

                    self.sync_product(product_data)
                    synced_count += 1

                    if limit and synced_count >= limit:
                        break

                except Exception as e:
                    error_count += 1
                    _logger.error('Failed to sync product: %s', str(e))
                    continue

            _logger.info(
                'Product sync completed: %d synced, %d errors',
                synced_count, error_count
            )

            return {
                'synced': synced_count,
                'errors': error_count,
            }

        except Exception as e:
            _logger.error('Product sync failed: %s', str(e))
            raise UserError(_('Product synchronization failed: %s') % str(e))

    def sync_product_by_id(self, dotykacka_product_id):
        """
        Sync a specific product by Dotykačka ID.

        Args:
            dotykacka_product_id (str): Dotykačka product ID

        Returns:
            product.product: Synced product record
        """
        self.ensure_one()
        oauth = self._get_oauth()
        endpoint = f'/v2/clouds/{self.config_id.cloud_id}/products/{dotykacka_product_id}'

        try:
            product_data = oauth.call_api('GET', endpoint)
            if product_data:
                return self.sync_product(product_data)
            else:
                raise UserError(_('Product not found in Dotykačka'))

        except Exception as e:
            _logger.error('Failed to sync product %s: %s', dotykacka_product_id, str(e))
            raise UserError(_('Failed to sync product: %s') % str(e))
