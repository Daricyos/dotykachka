# pylint:disable=all
"""Monkeypatch of odoo.http.HttpRequest for Odoo 18."""
import logging

from odoo.http import request

_logger = logging.getLogger(__name__)


def patch_json_request():
    """
    Эта функция применяет патч к request.get_json_data,
    чтобы обрабатывать тела JSON-запросов, являющиеся списками.
    """
    # Сохраняем оригинальный метод, чтобы избежать рекурсии
    _original_get_json_data = request.get_json_data()

    def _get_json_data_and_wrap_list(self, force=False):
        """Новый, исправленный метод."""
        json_data = _original_get_json_data(self, force=force)

        if isinstance(json_data, list):
            _logger.debug("Оборачиваем тело JSON-запроса (список) в {'items': ...}")
            return {'items': json_data}

        return json_data

    # Применяем монки-патч, заменяя старый метод новым
    request.get_json_data = _get_json_data_and_wrap_list
    _logger.info("request.get_json_data успешно исправлен для обработки списков.")
