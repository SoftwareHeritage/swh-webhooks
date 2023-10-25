# Copyright (C) 2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from datetime import datetime, timezone
import json

from swh.webhooks.utils import get_verified_webhook_payload, sign_webhook_payload


def test_sign_payload_and_verify():
    payload = {"foo": "bar"}
    payload_str = json.dumps(payload)
    now = datetime.now(tz=timezone.utc)
    msg_id = "msg_1234"
    secret = "whsec_" + "a" * 32

    signature = sign_webhook_payload(
        payload=payload_str, timestamp=now, msg_id=msg_id, secret=secret
    )

    assert (
        get_verified_webhook_payload(
            request_data=payload_str,
            request_headers={
                "Webhook-Id": msg_id,
                "Webhook-Timestamp": str(int(now.timestamp())),
                "Webhook-Signature": signature,
            },
            secret=secret,
        )
        == payload
    )
