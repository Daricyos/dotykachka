"""Module for Dotykacka Product Catalog synchronization."""
__version__ = "1.0"

import logging
import math

from odoo import _, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DotykackaProductCatalog(models.TransientModel):
    """Product catalog synchronization manager."""

    _name = 'dotykacka.product.catalog'
    _check_company_auto = True

    per_page = 50

    def get_vat(self, product_id) -> float:
        """
        Compute vat coeficient.

        :param product_id: product.product object
        """
        vat = product_id.taxes_id.filtered(lambda r: r.company_id.id == self.env.company.id)
        vat_coef = (vat.amount + 100) / 100
        return vat_coef

    def dotykacka_get_dataset(self, recordset):
        """
        Prepare data of each product in recordset.

        :param recordset: Recordset of product.product
        :return: list of dicts
        """
        data_lst = []
        for rec in recordset:
            if not rec.categ_id.dotykacka_category_id:
                raise ValidationError(
                    _("_categoryId is not set for category: %s") % rec.categ_id.complete_name
                )
            data = {
                "_categoryId": rec.categ_id.dotykacka_category_id,
                "deleted": False,
                "discountPercent": 0,
                "discountPermitted": True,
                "display": True,
                "flags": 0,
                "hexColor": "#FB8C00",
                "name": rec.display_name,
                "onSale": False,  # TD: budeme riesit pri zlavach
                "packaging": "1",
                "points": "0",
                "priceWithoutVat": 666666 / self.get_vat(rec),
                "requiresPriceEntry": False,
                "stockDeduct": False,
                "stockOverdraft": "ALLOW",
                "unit": "Piece",
                "vat": self.get_vat(rec),
                "externalId": rec.id,
            }
            if rec.barcode:
                data['ean'] = [rec.barcode]  # Must be list
            if rec.dotykacka_id:  # Needed for update
                data['id'] = rec.dotykacka_id
            data_lst.append(data)
        return data_lst

    def _dotykacka_create_products(self, product_ids_lst: list, company) -> bool:
        """
        Create product in dotykacka.

        :param: product_ids: list of product.product ids
        :param company: company object

        :return: bool True if success, False otherwise
        """
        self.env.company = company
        dotykacka_base = self.env['dotykacka.base']
        product_product = self.with_context(force_company=company.id).env['product.product']
        request_name = 'connector_dotykacka.api_request_dotykacka_create_product'
        request = self.env.ref(request_name)
        product_ids = product_product.browse(product_ids_lst)
        data_list = dotykacka_base.dotykacka_map_data(self._name, product_ids)
        cloud_id = self.env['api_manager.request_parameter'].search(
            [
                ('provider', '=', request.provider.id),
                ('key', '=', 'cloud_id'),
                ('company_id', '=', self.env.company.id),
            ]
        )
        response = request.send_request_dotykacka(
            params={"{cloud_id}": cloud_id.value}, data=data_list, return_type='decoded'
        )
        for item in response:
            dotykacka_base.write_metadata(product_product, item, company)

        return bool(response)

    def _dotykacka_write_products(self, product_ids: list, company) -> bool:  # pylint:disable=R0914
        """
        Write products in dotykacka.

        :param: product_ids: list of product.product dotykacka_ids
        :param: company: company object

        :return: bool True if success, False otherwise
        """
        self.env.company = company
        dotykacka_base = self.env['dotykacka.base']
        product_product = self.with_context(force_company=company.id).env['product.product']
        request_put = self.env.ref('connector_dotykacka.api_request_dotykacka_write_products')
        request_get = self.env.ref('connector_dotykacka.api_request_dotykacka_get_products')
        products = product_product.browse(product_ids)
        product_dotykacka_ids = products.mapped('dotykacka_id')
        # Do not process on empty records.
        if not product_dotykacka_ids:
            return False
        ids_string = ','.join(str(a) for a in product_dotykacka_ids)
        filter_request = f"?filter=id|in|{ids_string}&limit={self.per_page}"
        cloud_id = self.env['api_manager.request_parameter'].search(
            [
                ('provider', '=', request_get.provider.id),
                ('key', '=', 'cloud_id'),
                ('company_id', '=', self.env.company.id),
            ]
        )
        # Get ETag for product
        dotykacka_response = request_get.send_request_dotykacka(
            params={"{cloud_id}": cloud_id.value, "{filter}": filter_request}, return_type='decoded'
        )
        # Dotykacka returns items in different order as requested, here we are sorting our
        # recordset to match returned order.
        products_sorted = self.with_context(force_company=company.id).env['product.product']
        # pylint:disable=W0640, W0631
        for item in dotykacka_response['data']:
            products_sorted += products.filtered(lambda r: r.dotykacka_id == item['id'])

        dotykacka_etag = request_get.response.headers['ETag'].replace('"', '')
        request_put._headers['If-Match'] = dotykacka_etag  # pylint:disable=W0212
        data_list = dotykacka_base.dotykacka_map_data(self._name, products_sorted)
        response = request_put.send_request_dotykacka(
            params={
                "{cloud_id}": cloud_id.value,
            },
            data=data_list,
            return_type='decoded',
        )
        if not response:
            return False
        for item in response:
            dotykacka_base.write_metadata(product_product, item, company)
        return bool(response)

    def create_products(self, products, company):
        """
        Create products in dotykacka.

        :param products: product.product recordset
        :param company: company object
        """
        existing_products = self._check_existing_products(products.mapped('id'), company)
        products -= existing_products
        product_ids_create = products.mapped('id')
        self._create_write_iter('create', product_ids_create, company)

    def update_products(self, products, company):
        """
        Update products in dotykacka.

        :param products: product.product recordset
        :param company: company object
        """
        product_ids_update = products.mapped('id')
        self._create_write_iter('write', product_ids_update, company)

    def _check_existing_products(self, product_ids: list, company):
        """
        Sync existing product in dotykacka.

        :param product_ids: list of product.product ids
        :param company: company object

        :return: product.product recordset of existing products in dotykacka
        """
        self.env.company = company
        request = self.env.ref('connector_dotykacka.api_request_dotykacka_get_products')
        cloud_id = self.env['api_manager.request_parameter'].search(
            [
                ('provider', '=', request.provider.id),
                ('key', '=', 'cloud_id'),
                ('company_id', '=', self.env.company.id),
            ]
        )

        page = 0
        per_page = 50
        last_page = math.ceil(len(product_ids) / per_page)
        result = self.with_context(force_company=company.id).env['product.product']

        while page < last_page:
            limit = page * per_page
            ids = product_ids[limit : limit + per_page]
            products = request.send_request_dotykacka(
                params={
                    "{cloud_id}": cloud_id.value,
                    "{filter}": f"?filter%3DexternalId%7Cin%7C{(','.join(str(a) for a in ids))}",
                },
                return_type='decoded',
            )
            result += self._process_dotykacka_products_in_odoo(products, False, company)

            page += 1
        return result

    # pylama:ignore=W0212
    def _create_write_iter(self, method_type, product_ids: list, company):
        """
        Calculate paging of products sent to dotykacka.

        :param method_type: str 'create'/'write' method to call
        :param product_ids: list of product.product ids
        :param company: company object
        """
        pages = self._compute_paging(len(product_ids))
        iteration = 1
        processed_products = 0
        pages_overflow = pages[1] != 0
        pages_total = pages[0] if not pages_overflow else pages[0] + 1
        while iteration <= pages_total:
            pages_end = (
                processed_products + pages[1]
                if pages_overflow and iteration == pages_total
                else processed_products + self.per_page
            )
            products_slice = product_ids[processed_products:pages_end]
            if not products_slice:
                processed_products = iteration * self.per_page
                iteration += 1
                continue

            if method_type == 'create':
                self.with_context(dotykacka_noupdate=True)._dotykacka_create_products(
                    products_slice, company
                )
            elif method_type == 'write':
                self.with_context(dotykacka_noupdate=True)._dotykacka_write_products(
                    products_slice, company
                )

            processed_products = iteration * self.per_page
            iteration += 1

    # pylama:ignore=C901
    def _process_dotykacka_products_in_odoo(self, products, update: bool, company):
        """
        Update odoo record dotykacka_id to match dotykacka.

        :param products: List of dotykacka products
        :param update: Update product in dotykacka
        :param company: company object

        :return: product.product recordset
        """
        recordset = self.with_context(force_company=company.id).env['product.product']
        if not products:
            return recordset
        for product in products['data']:
            product_id = False
            # If data has an EAN, search for product
            if product['ean']:
                product_id = (
                    self.with_context(force_company=company.id)
                    .env['product.product']
                    .search([('barcode', 'in', product['ean'])])
                )
            elif product['externalId'] is not None:
                product_id = (
                    self.with_context(force_company=company.id)
                    .env['product.product']
                    .search([('id', '=', product['externalId'])])
                )
            else:
                _logger.warning(
                    "Product %s %s has no EAN nor External ID set", product['id'], product['name']
                )
            if product_id:
                if product_id.dotykacka_sync_disabled:
                    continue
                dotykacka_base = self.env['dotykacka.base']
                if not product_id.dotykacka_id:
                    dotykacka_base.write_metadata(product_id, product, company)
                    if product['externalId'] != product_id.id:
                        recordset += product_id
                else:
                    if product_id.dotykacka_id != product['id']:
                        dotykacka_base.write_metadata(product_id, product, company)
        if update:
            self._dotykacka_write_products(recordset.ids, company)
        return recordset

    @classmethod
    def _compute_paging(cls, count: int) -> list:
        """
        Compute paging for recordset.

        :param count: total number of items to process

        :return: list (pages, overflow)
        """
        return (count // cls.per_page, count % cls.per_page)

    def sync_products_to_dotykacka(self, product_id):
        """
        Synchronize products to dotykacka in case of needs.

        :param product_id: product object
        """
        if product_id.dotykacka_sync_disabled:
            raise ValidationError(
                _(
                    "Product %s is marked as Disabled Dotykacka Synchronization, "
                    "correct this product manually."
                )
                % product_id.display_name
            )
        if not product_id.dotykacka_id:
            self.env['dotykacka.product.catalog'].sudo().create_products(
                product_id, self.env.company
            )
        if product_id.dotykacka_id and not product_id.dotykacka_exported:
            self.env['dotykacka.product.catalog'].sudo().update_products(
                product_id, self.env.company
            )
        if not product_id.dotykacka_exported and not product_id.dotykacka_id:
            raise ValidationError(
                _("Product %s is not synced to dotykacka.") % product_id.display_name
            )
