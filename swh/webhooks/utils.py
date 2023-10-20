# Copyright (C) 2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from typing import Any, Dict, Union

from svix.webhooks import Webhook, WebhookVerificationError


def get_verified_webhook_payload(
    request_data: Union[bytes, str], request_headers: Dict[str, str], secret: str
) -> Dict[str, Any]:
    """Verify the authenticity of a webhook message and returns JSON payload.

    Args:
        request_data: Body of received POST request
        request_hedaers: Headers of received POST request

    Returns:
        JSON payload as a dict

    Raises:
        ValueError: Webhook content verification failed
    """
    webhook = Webhook(secret)
    try:
        return webhook.verify(request_data, request_headers)
    except WebhookVerificationError:
        raise ValueError("Webhook payload verification failed")