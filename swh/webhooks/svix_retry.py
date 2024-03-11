# Copyright (C) 2024  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import logging

from httpx import ConnectError, TimeoutException
from svix.internal.openapi_client.errors import UnexpectedStatus
from tenacity import retry
from tenacity.before_sleep import before_sleep_log
from tenacity.retry import retry_if_exception
from tenacity.stop import stop_after_attempt
from tenacity.wait import wait_exponential

SVIX_RETRY_WAIT_EXP_BASE = 10
SVIX_RETRY_MAX_ATTEMPTS = 3

logger = logging.getLogger(__name__)


def is_retryable_exception(exception):
    return isinstance(exception, (ConnectError, TimeoutException, UnexpectedStatus))


def svix_retry():
    """Enable to retry a call to the Svix API in case of temporary network failure."""
    return retry(
        retry=retry_if_exception(is_retryable_exception),
        wait=wait_exponential(exp_base=SVIX_RETRY_WAIT_EXP_BASE),
        stop=stop_after_attempt(max_attempt_number=SVIX_RETRY_MAX_ATTEMPTS),
        before_sleep=before_sleep_log(logger, logging.DEBUG),
        reraise=True,
    )
