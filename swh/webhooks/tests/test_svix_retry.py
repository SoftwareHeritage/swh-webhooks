# Copyright (C) 2024  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information


import pytest
from svix.api.errors.http_error import HttpError

from swh.webhooks.svix_retry import SVIX_RETRY_MAX_ATTEMPTS, SVIX_RETRY_WAIT_EXP_BASE


def assert_sleep_calls(mock_sleep, mocker, nb_failures):
    mock_sleep.assert_has_calls(
        [
            mocker.call(param)
            for param in [SVIX_RETRY_WAIT_EXP_BASE**i for i in range(nb_failures)]
        ]
    )


def test_event_send_retry(swh_webhooks, origin_create_event_type, mocker, mock_sleep):
    swh_webhooks.event_type_create(origin_create_event_type)
    event_type = swh_webhooks.event_type_get(origin_create_event_type.name)

    event_type_get = mocker.patch.object(swh_webhooks, "event_type_get")
    event_type_get.side_effect = [
        HttpError.from_dict({"code": 503}),
        HttpError.from_dict({"code": 503}),
        event_type,
    ]

    assert swh_webhooks.event_send(
        origin_create_event_type.name,
        {"origin_url": "https://example.org/user/project"},
    )

    assert_sleep_calls(mock_sleep, mocker, nb_failures=2)


def test_event_send_retry_and_reraise(swh_webhooks, origin_create_event_type, mocker):
    event_type_get = mocker.patch.object(swh_webhooks, "event_type_get")
    event_type_get.side_effect = [
        HttpError.from_dict({"code": 500}),
    ] * SVIX_RETRY_MAX_ATTEMPTS

    with pytest.raises(HttpError):
        swh_webhooks.event_send(
            origin_create_event_type.name,
            {"origin_url": "https://example.org/user/project"},
        )
