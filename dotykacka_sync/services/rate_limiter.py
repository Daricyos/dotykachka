"""Rate Limiter for Dotykačka API."""

import logging
import time
from collections import deque
from datetime import datetime, timedelta

from odoo import models

_logger = logging.getLogger(__name__)


class DotykackaRateLimiter(models.AbstractModel):
    """
    Rate limiter to respect Dotykačka API limits.

    Dotykačka API limit: ~150 requests per 30 minutes
    """

    _name = 'dotykacka.rate.limiter'
    _description = 'Dotykačka Rate Limiter'

    _request_history = {}  # config_id -> deque of timestamps

    def _get_request_history(self, config):
        """Get or initialize request history for config."""
        if config.id not in self._request_history:
            self._request_history[config.id] = deque()
        return self._request_history[config.id]

    def _clean_old_requests(self, config):
        """Remove requests older than rate limit period."""
        history = self._get_request_history(config)
        cutoff_time = time.time() - config.rate_limit_period

        while history and history[0] < cutoff_time:
            history.popleft()

    def can_make_request(self, config):
        """
        Check if we can make a request without exceeding rate limit.

        Args:
            config: dotykacka.config record

        Returns:
            bool: True if request can be made
        """
        self._clean_old_requests(config)
        history = self._get_request_history(config)

        return len(history) < config.rate_limit_requests

    def wait_if_needed(self, config):
        """
        Wait if necessary to respect rate limit.

        Args:
            config: dotykacka.config record

        Returns:
            float: Time waited in seconds
        """
        self._clean_old_requests(config)
        history = self._get_request_history(config)

        if len(history) < config.rate_limit_requests:
            return 0.0

        # Need to wait until oldest request expires
        oldest_request = history[0]
        wait_until = oldest_request + config.rate_limit_period
        wait_time = wait_until - time.time()

        if wait_time > 0:
            _logger.info(
                'Rate limit reached for config %s. Waiting %.2f seconds...',
                config.cloud_id,
                wait_time
            )
            time.sleep(wait_time)
            self._clean_old_requests(config)
            return wait_time

        return 0.0

    def record_request(self, config):
        """
        Record that a request was made.

        Args:
            config: dotykacka.config record
        """
        history = self._get_request_history(config)
        history.append(time.time())

    def get_remaining_requests(self, config):
        """
        Get number of requests remaining in current period.

        Args:
            config: dotykacka.config record

        Returns:
            int: Number of requests that can be made
        """
        self._clean_old_requests(config)
        history = self._get_request_history(config)

        return max(0, config.rate_limit_requests - len(history))

    def get_reset_time(self, config):
        """
        Get time when rate limit will reset.

        Args:
            config: dotykacka.config record

        Returns:
            datetime: When the oldest request will expire
        """
        self._clean_old_requests(config)
        history = self._get_request_history(config)

        if not history:
            return datetime.now()

        oldest_request = history[0]
        reset_timestamp = oldest_request + config.rate_limit_period

        return datetime.fromtimestamp(reset_timestamp)

    def clear_history(self, config):
        """
        Clear request history for config.

        Args:
            config: dotykacka.config record
        """
        if config.id in self._request_history:
            del self._request_history[config.id]

        _logger.info('Cleared rate limit history for config %s', config.cloud_id)
