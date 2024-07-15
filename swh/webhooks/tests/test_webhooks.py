# Copyright (C) 2023-2024  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from datetime import datetime, timezone
from itertools import chain
import random
import time

from jsonschema.exceptions import SchemaError, ValidationError
import pytest
from werkzeug import Request, Response

from swh.webhooks.interface import Endpoint, EventType
from swh.webhooks.utils import get_verified_webhook_payload

WEBHOOK_FIRST_ENDPOINT_PATH = "/swh/webhook"
WEBHOOK_SECOND_ENDPOINT_PATH = "/swh/webhook/other"
WEBHOOK_THIRD_ENDPOINT_PATH = "/swh/webhook/another"

FIRST_GIT_ORIGIN_URL = "https://git.example.org/user/project"
SECOND_GIT_ORIGIN_URL = "https://git.example.org/user/project2"


def _endpoint(httpserver, event_type, endpoint_path, channel=None):
    return Endpoint(
        event_type_name=event_type.name,
        url=httpserver.url_for(endpoint_path),
        channel=channel,
    )


@pytest.fixture
def origin_create_endpoint1_no_channel(origin_create_event_type, httpserver):
    return _endpoint(httpserver, origin_create_event_type, WEBHOOK_FIRST_ENDPOINT_PATH)


@pytest.fixture
def origin_create_endpoint2_no_channel(origin_create_event_type, httpserver):
    return _endpoint(httpserver, origin_create_event_type, WEBHOOK_SECOND_ENDPOINT_PATH)


@pytest.fixture
def origin_visit_endpoint1_channel1(origin_visit_event_type, httpserver):
    return _endpoint(
        httpserver,
        origin_visit_event_type,
        WEBHOOK_FIRST_ENDPOINT_PATH,
        channel=FIRST_GIT_ORIGIN_URL,
    )


@pytest.fixture
def origin_visit_endpoint2_channel2(origin_visit_event_type, httpserver):
    return _endpoint(
        httpserver,
        origin_visit_event_type,
        WEBHOOK_SECOND_ENDPOINT_PATH,
        channel=SECOND_GIT_ORIGIN_URL,
    )


@pytest.fixture
def origin_visit_endpoint3_no_channel(origin_visit_event_type, httpserver):
    return _endpoint(
        httpserver,
        origin_visit_event_type,
        WEBHOOK_THIRD_ENDPOINT_PATH,
    )


def origin_create_payload(origin_url):
    return {"origin_url": origin_url}


def origin_visit_payload(origin_url, visit_type, visit_status, snapshot_swhid):
    return {
        "origin_url": origin_url,
        "visit_type": visit_type,
        "visit_date": datetime.now().isoformat(),
        "visit_status": visit_status,
        "snapshot_swhid": snapshot_swhid,
    }


def random_snapshot_swhid():
    random_sha1 = "".join(random.choice("0123456789abcdef") for i in range(40))
    return f"swh:1:snp:{random_sha1}"


def test_create_valid_event_type(swh_webhooks, origin_create_event_type):
    swh_webhooks.event_type_create(origin_create_event_type)
    assert (
        swh_webhooks.event_type_get(origin_create_event_type.name)
        == origin_create_event_type
    )
    event_types = swh_webhooks.event_types_list()
    assert event_types
    assert event_types[0] == origin_create_event_type

    # check update
    swh_webhooks.event_type_create(origin_create_event_type)


def test_get_invalid_event_type(swh_webhooks):
    with pytest.raises(ValueError, match="Event type foo.bar does not exist"):
        swh_webhooks.event_type_get("foo.bar")


def test_create_invalid_event_type(swh_webhooks):
    with pytest.raises(
        ValueError, match="Event type name must be in the form '<group>.<event>'"
    ):
        swh_webhooks.event_type_create(
            EventType(name="origin", description="", schema={})
        )

    with pytest.raises(
        SchemaError, match="'obj' is not valid under any of the given schemas"
    ):
        swh_webhooks.event_type_create(
            EventType(name="origin.create", description="", schema={"type": "obj"})
        )


def test_create_numerous_event_types(swh_webhooks):
    event_types = []
    for i in range(100):
        event_type = EventType(
            name=f"event.test{i:03}",
            description="",
            schema={"type": "object"},
        )
        event_types.append(event_type)
        swh_webhooks.event_type_create(event_type)
    assert swh_webhooks.event_types_list() == event_types


def test_delete_event_type(swh_webhooks, origin_create_event_type):
    swh_webhooks.event_type_create(origin_create_event_type)
    swh_webhooks.event_type_delete(origin_create_event_type.name)
    assert swh_webhooks.event_types_list() == []


def test_delete_invalid_event_type(swh_webhooks):
    with pytest.raises(ValueError, match="Event type foo.bar does not exist"):
        swh_webhooks.event_type_delete("foo.bar")


def test_create_endpoints(
    swh_webhooks,
    origin_create_event_type,
    origin_visit_event_type,
    origin_create_endpoint1_no_channel,
    origin_visit_endpoint1_channel1,
):
    swh_webhooks.event_type_create(origin_create_event_type)
    swh_webhooks.event_type_create(origin_visit_event_type)

    swh_webhooks.endpoint_create(origin_create_endpoint1_no_channel)
    swh_webhooks.endpoint_create(origin_visit_endpoint1_channel1)

    secret_create = swh_webhooks.endpoint_get_secret(origin_create_endpoint1_no_channel)
    assert secret_create.startswith("whsec_")

    secret_visit = swh_webhooks.endpoint_get_secret(origin_visit_endpoint1_channel1)
    assert secret_visit.startswith("whsec_")


def test_create_endpoints_with_secret(
    swh_webhooks,
    origin_create_event_type,
    origin_visit_event_type,
    origin_create_endpoint1_no_channel,
    origin_visit_endpoint1_channel1,
):
    swh_webhooks.event_type_create(origin_create_event_type)
    swh_webhooks.event_type_create(origin_visit_event_type)

    secret_create = "whsec_" + "a" * 32
    swh_webhooks.endpoint_create(
        origin_create_endpoint1_no_channel, secret=secret_create
    )
    secret_visit = "whsec_" + "b" * 32
    swh_webhooks.endpoint_create(origin_visit_endpoint1_channel1, secret=secret_visit)

    assert (
        swh_webhooks.endpoint_get_secret(origin_create_endpoint1_no_channel)
        == secret_create
    )

    assert (
        swh_webhooks.endpoint_get_secret(origin_visit_endpoint1_channel1)
        == secret_visit
    )


def test_create_endpoint_and_update_secret(
    swh_webhooks,
    origin_visit_event_type,
    origin_visit_endpoint1_channel1,
):
    swh_webhooks.event_type_create(origin_visit_event_type)

    # explicitly set a secret for the endpoint
    first_secret = "whsec_" + "a" * 32
    swh_webhooks.endpoint_create(origin_visit_endpoint1_channel1, secret=first_secret)
    assert (
        swh_webhooks.endpoint_get_secret(origin_visit_endpoint1_channel1)
        == first_secret
    )

    # explicitly update a secret for the endpoint
    second_secret = "whsec_" + "b" * 32
    swh_webhooks.endpoint_create(origin_visit_endpoint1_channel1, secret=second_secret)

    assert (
        swh_webhooks.endpoint_get_secret(origin_visit_endpoint1_channel1)
        == second_secret
    )

    # updating an endpoint without an explicit secret should generate a new one
    swh_webhooks.endpoint_create(origin_visit_endpoint1_channel1)
    assert swh_webhooks.endpoint_get_secret(origin_visit_endpoint1_channel1) not in (
        first_secret,
        second_secret,
    )


def test_list_endpoints(
    swh_webhooks,
    origin_create_event_type,
    origin_visit_event_type,
    origin_create_endpoint1_no_channel,
    origin_create_endpoint2_no_channel,
    origin_visit_endpoint1_channel1,
    origin_visit_endpoint2_channel2,
    origin_visit_endpoint3_no_channel,
):
    swh_webhooks.event_type_create(origin_create_event_type)
    swh_webhooks.event_type_create(origin_visit_event_type)

    swh_webhooks.endpoint_create(origin_create_endpoint1_no_channel)
    swh_webhooks.endpoint_create(origin_create_endpoint2_no_channel)
    swh_webhooks.endpoint_create(origin_visit_endpoint1_channel1)
    swh_webhooks.endpoint_create(origin_visit_endpoint2_channel2)
    swh_webhooks.endpoint_create(origin_visit_endpoint3_no_channel)

    assert list(
        swh_webhooks.endpoints_list(origin_create_event_type.name, ascending_order=True)
    ) == [
        origin_create_endpoint1_no_channel,
        origin_create_endpoint2_no_channel,
    ]

    assert list(swh_webhooks.endpoints_list(origin_visit_event_type.name)) == [
        origin_visit_endpoint3_no_channel
    ]

    assert list(
        swh_webhooks.endpoints_list(
            origin_visit_event_type.name, channel=FIRST_GIT_ORIGIN_URL
        )
    ) == [origin_visit_endpoint3_no_channel, origin_visit_endpoint1_channel1]

    assert list(
        swh_webhooks.endpoints_list(
            origin_visit_event_type.name, channel=SECOND_GIT_ORIGIN_URL
        )
    ) == [origin_visit_endpoint3_no_channel, origin_visit_endpoint2_channel2]


def test_create_numerous_endpoints_and_list(swh_webhooks, origin_create_event_type):
    swh_webhooks.event_type_create(origin_create_event_type)

    endpoints = [
        Endpoint(
            url=f"https://example.com/webhook{i}",
            event_type_name=origin_create_event_type.name,
        )
        for i in range(100)
    ]

    for endpoint in endpoints:
        swh_webhooks.endpoint_create(endpoint)

    assert list(swh_webhooks.endpoints_list(origin_create_event_type.name)) == list(
        reversed(endpoints)
    )

    assert (
        list(
            swh_webhooks.endpoints_list(
                origin_create_event_type.name, ascending_order=True
            )
        )
        == endpoints
    )

    assert (
        list(
            swh_webhooks.endpoints_list(
                origin_create_event_type.name, ascending_order=True, limit=30
            )
        )
        == endpoints[:30]
    )


def test_get_endpoint_not_found(swh_webhooks, origin_create_event_type):
    swh_webhooks.event_type_create(origin_create_event_type)

    unknown_endpoint = Endpoint(
        url="https://example.com/webhook",
        event_type_name=origin_create_event_type.name,
    )

    error_message = (
        f"Endpoint with url {unknown_endpoint.url} for event type "
        f"{unknown_endpoint.event_type_name} does not exist"
    )

    with pytest.raises(ValueError, match=error_message):
        swh_webhooks.endpoint_get_secret(unknown_endpoint)

    with pytest.raises(ValueError, match=error_message):
        swh_webhooks.endpoint_delete(unknown_endpoint)


def test_delete_endpoint(
    swh_webhooks,
    origin_create_event_type,
    origin_create_endpoint1_no_channel,
    origin_create_endpoint2_no_channel,
):
    swh_webhooks.event_type_create(origin_create_event_type)

    swh_webhooks.endpoint_create(origin_create_endpoint1_no_channel)
    swh_webhooks.endpoint_create(origin_create_endpoint2_no_channel)

    swh_webhooks.endpoint_delete(origin_create_endpoint2_no_channel)

    assert list(swh_webhooks.endpoints_list(origin_create_event_type.name)) == [
        origin_create_endpoint1_no_channel
    ]


def test_send_event_invalid_event_type(swh_webhooks):
    with pytest.raises(ValueError, match="Event type foo.bar does not exist"):
        swh_webhooks.event_send("foo.bar", {})


def test_send_event_invalid_payload(
    swh_webhooks,
    origin_visit_event_type,
):
    payload = origin_visit_payload(
        origin_url=FIRST_GIT_ORIGIN_URL,
        visit_type="git",
        visit_status="full",
        snapshot_swhid="invalid_swhid",
    )

    swh_webhooks.event_type_create(origin_visit_event_type)

    with pytest.raises(ValidationError, match="'invalid_swhid' does not match"):
        swh_webhooks.event_send(origin_visit_event_type.name, payload)


def test_send_event_without_channels_filtering(
    swh_webhooks,
    origin_create_event_type,
    origin_create_endpoint1_no_channel,
    origin_create_endpoint2_no_channel,
    httpserver,
):
    swh_webhooks.event_type_create(origin_create_event_type)
    swh_webhooks.endpoint_create(origin_create_endpoint1_no_channel)
    swh_webhooks.endpoint_create(origin_create_endpoint2_no_channel)

    origin_create_endpoint1_no_channel_secret = swh_webhooks.endpoint_get_secret(
        origin_create_endpoint1_no_channel
    )
    origin_create_endpoint2_no_channel_secret = swh_webhooks.endpoint_get_secret(
        origin_create_endpoint2_no_channel
    )

    request_headers = {}
    request_payloads = {}

    def handler(request: Request) -> Response:
        assert "Webhook-Id" in request.headers
        assert "Webhook-Timestamp" in request.headers
        assert "Webhook-Signature" in request.headers

        if request.url.endswith(WEBHOOK_FIRST_ENDPOINT_PATH):
            payload = get_verified_webhook_payload(
                request.data, request.headers, origin_create_endpoint1_no_channel_secret
            )
        else:
            payload = get_verified_webhook_payload(
                request.data, request.headers, origin_create_endpoint2_no_channel_secret
            )

        key = (request.url, request.headers["Webhook-Id"])
        request_headers[key] = dict(request.headers)
        request_payloads[key] = payload

        return Response("OK")

    first_origin_create_payload = origin_create_payload(FIRST_GIT_ORIGIN_URL)
    second_origin_create_payload = origin_create_payload(SECOND_GIT_ORIGIN_URL)

    httpserver.expect_oneshot_request(
        WEBHOOK_FIRST_ENDPOINT_PATH,
        method="POST",
        json=first_origin_create_payload,
    ).respond_with_handler(handler)

    httpserver.expect_oneshot_request(
        WEBHOOK_SECOND_ENDPOINT_PATH,
        method="POST",
        json=first_origin_create_payload,
    ).respond_with_handler(handler)

    httpserver.expect_oneshot_request(
        WEBHOOK_FIRST_ENDPOINT_PATH,
        method="POST",
        json=second_origin_create_payload,
    ).respond_with_handler(handler)

    httpserver.expect_oneshot_request(
        WEBHOOK_SECOND_ENDPOINT_PATH,
        method="POST",
        json=second_origin_create_payload,
    ).respond_with_handler(handler)

    with httpserver.wait() as waiting:
        swh_webhooks.event_send(
            origin_create_event_type.name, first_origin_create_payload
        )
        swh_webhooks.event_send(
            origin_create_event_type.name, second_origin_create_payload
        )

    assert waiting.result

    httpserver.check()

    for sent_event in chain(
        swh_webhooks.sent_events_list_for_endpoint(origin_create_endpoint1_no_channel),
        swh_webhooks.sent_events_list_for_endpoint(origin_create_endpoint2_no_channel),
        swh_webhooks.sent_events_list_for_event_type(origin_create_event_type.name),
    ):
        assert sent_event.event_type_name == origin_create_event_type.name
        assert sent_event.channel is None
        assert sent_event.endpoint_url in (
            origin_create_endpoint1_no_channel.url,
            origin_create_endpoint2_no_channel.url,
        )
        assert sent_event.response == "OK"
        assert sent_event.response_status_code == 200
        key = (sent_event.endpoint_url, sent_event.msg_id)
        assert sent_event.payload == request_payloads[key]
        assert (
            set(sent_event.headers.items()) - set(request_headers[key].items()) == set()
        )


def test_send_event_with_channels_filtering(
    swh_webhooks,
    origin_visit_event_type,
    origin_visit_endpoint1_channel1,
    origin_visit_endpoint2_channel2,
    origin_visit_endpoint3_no_channel,
    httpserver,
):
    swh_webhooks.event_type_create(origin_visit_event_type)
    swh_webhooks.endpoint_create(origin_visit_endpoint1_channel1)
    swh_webhooks.endpoint_create(origin_visit_endpoint2_channel2)
    swh_webhooks.endpoint_create(origin_visit_endpoint3_no_channel)

    origin_visit_endpoint1_channel1_secret = swh_webhooks.endpoint_get_secret(
        origin_visit_endpoint1_channel1
    )
    origin_visit_endpoint2_channel2_secret = swh_webhooks.endpoint_get_secret(
        origin_visit_endpoint2_channel2
    )

    origin_visit_endpoint3_no_channel_secret = swh_webhooks.endpoint_get_secret(
        origin_visit_endpoint3_no_channel
    )
    request_headers = {}
    request_payloads = {}

    def handler(request: Request) -> Response:
        assert "Webhook-Id" in request.headers
        assert "Webhook-Timestamp" in request.headers
        assert "Webhook-Signature" in request.headers

        if request.url.endswith(WEBHOOK_FIRST_ENDPOINT_PATH):
            payload = get_verified_webhook_payload(
                request.data, request.headers, origin_visit_endpoint1_channel1_secret
            )
        elif request.url.endswith(WEBHOOK_SECOND_ENDPOINT_PATH):
            payload = get_verified_webhook_payload(
                request.data, request.headers, origin_visit_endpoint2_channel2_secret
            )
        else:
            payload = get_verified_webhook_payload(
                request.data, request.headers, origin_visit_endpoint3_no_channel_secret
            )

        key = (request.url, request.headers["Webhook-Id"])
        request_headers[key] = dict(request.headers)
        request_payloads[key] = payload

        return Response("OK")

    first_origin_visit_payload = origin_visit_payload(
        origin_url=FIRST_GIT_ORIGIN_URL,
        visit_type="git",
        visit_status="full",
        snapshot_swhid=random_snapshot_swhid(),
    )
    second_origin_visit_payload = origin_visit_payload(
        origin_url=SECOND_GIT_ORIGIN_URL,
        visit_type="git",
        visit_status="failed",
        snapshot_swhid=None,
    )

    httpserver.expect_oneshot_request(
        WEBHOOK_FIRST_ENDPOINT_PATH,
        method="POST",
        json=first_origin_visit_payload,
    ).respond_with_handler(handler)

    httpserver.expect_oneshot_request(
        WEBHOOK_THIRD_ENDPOINT_PATH,
        method="POST",
        json=first_origin_visit_payload,
    ).respond_with_handler(handler)

    httpserver.expect_oneshot_request(
        WEBHOOK_SECOND_ENDPOINT_PATH,
        method="POST",
        json=second_origin_visit_payload,
    ).respond_with_handler(handler)

    httpserver.expect_oneshot_request(
        WEBHOOK_THIRD_ENDPOINT_PATH,
        method="POST",
        json=second_origin_visit_payload,
    ).respond_with_handler(handler)

    with httpserver.wait() as waiting:
        swh_webhooks.event_send(
            origin_visit_event_type.name,
            first_origin_visit_payload,
            channel=FIRST_GIT_ORIGIN_URL,
        )
        swh_webhooks.event_send(
            origin_visit_event_type.name,
            second_origin_visit_payload,
            channel=SECOND_GIT_ORIGIN_URL,
        )

    assert waiting.result

    httpserver.check()

    for sent_event in chain(
        swh_webhooks.sent_events_list_for_endpoint(origin_visit_endpoint1_channel1),
        swh_webhooks.sent_events_list_for_endpoint(origin_visit_endpoint2_channel2),
        swh_webhooks.sent_events_list_for_endpoint(origin_visit_endpoint3_no_channel),
        swh_webhooks.sent_events_list_for_event_type(origin_visit_event_type.name),
    ):
        assert sent_event.event_type_name == origin_visit_event_type.name
        assert sent_event.channel in (FIRST_GIT_ORIGIN_URL, SECOND_GIT_ORIGIN_URL, None)
        assert sent_event.endpoint_url in (
            origin_visit_endpoint1_channel1.url,
            origin_visit_endpoint2_channel2.url,
            origin_visit_endpoint3_no_channel.url,
        )
        assert sent_event.response == "OK"
        assert sent_event.response_status_code == 200
        key = (sent_event.endpoint_url, sent_event.msg_id)
        assert sent_event.payload == request_payloads[key]
        assert (
            set(sent_event.headers.items()) - set(request_headers[key].items()) == set()
        )

    assert {
        event.channel
        for event in swh_webhooks.sent_events_list_for_event_type(
            origin_visit_event_type.name
        )
    } == {None, FIRST_GIT_ORIGIN_URL, SECOND_GIT_ORIGIN_URL}

    assert {
        event.channel
        for event in swh_webhooks.sent_events_list_for_event_type(
            origin_visit_event_type.name, channel=FIRST_GIT_ORIGIN_URL
        )
    } == {None, FIRST_GIT_ORIGIN_URL}

    assert {
        event.channel
        for event in swh_webhooks.sent_events_list_for_event_type(
            origin_visit_event_type.name, channel=SECOND_GIT_ORIGIN_URL
        )
    } == {None, SECOND_GIT_ORIGIN_URL}


def test_list_sent_events_date_filtering(
    swh_webhooks,
    origin_create_event_type,
    origin_create_endpoint1_no_channel,
    httpserver,
    mocker,
    mock_sleep,
):
    mocker.stop(mock_sleep)

    swh_webhooks.event_type_create(origin_create_event_type)
    swh_webhooks.endpoint_create(origin_create_endpoint1_no_channel)

    first_origin_create_payload = origin_create_payload(FIRST_GIT_ORIGIN_URL)

    httpserver.expect_oneshot_request(
        WEBHOOK_FIRST_ENDPOINT_PATH,
        method="POST",
        json=first_origin_create_payload,
    ).respond_with_data("OK")

    with httpserver.wait():
        swh_webhooks.event_send(
            origin_create_event_type.name, first_origin_create_payload
        )

    time.sleep(1)
    date = datetime.now(tz=timezone.utc)

    httpserver.expect_oneshot_request(
        WEBHOOK_FIRST_ENDPOINT_PATH,
        method="POST",
        json=first_origin_create_payload,
    ).respond_with_data("OK")

    with httpserver.wait():
        swh_webhooks.event_send(
            origin_create_event_type.name, first_origin_create_payload
        )

    sent_events_before = list(
        swh_webhooks.sent_events_list_for_endpoint(
            origin_create_endpoint1_no_channel, before=date
        )
    )

    sent_events_after = list(
        swh_webhooks.sent_events_list_for_endpoint(
            origin_create_endpoint1_no_channel, after=date
        )
    )

    assert len(sent_events_before) == 1
    assert len(sent_events_after) == 1

    assert sent_events_before != sent_events_after

    sent_events_before = list(
        swh_webhooks.sent_events_list_for_event_type(
            origin_create_event_type.name, before=date
        )
    )

    sent_events_after = list(
        swh_webhooks.sent_events_list_for_event_type(
            origin_create_event_type.name, after=date
        )
    )

    assert len(sent_events_before) == 1
    assert len(sent_events_after) == 1

    assert sent_events_before != sent_events_after


@pytest.mark.parametrize("limit", [1, 5, 10], ids=lambda li: f"limit={li}")
def test_list_sent_events_with_limit(
    swh_webhooks,
    origin_create_event_type,
    origin_create_endpoint1_no_channel,
    httpserver,
    limit,
):
    swh_webhooks.event_type_create(origin_create_event_type)
    swh_webhooks.endpoint_create(origin_create_endpoint1_no_channel)

    nb_origins = 100

    for i in range(nb_origins):
        httpserver.expect_oneshot_request(
            WEBHOOK_FIRST_ENDPOINT_PATH,
            method="POST",
        ).respond_with_data("OK")

    with httpserver.wait() as waiting:
        for i in range(nb_origins):
            payload = origin_create_payload(f"https://git.example.org/project{i}")
            swh_webhooks.event_send(origin_create_event_type.name, payload)

    assert waiting.result

    assert (
        len(
            list(
                swh_webhooks.sent_events_list_for_endpoint(
                    origin_create_endpoint1_no_channel, limit=limit
                )
            )
        )
        == limit
    )

    assert (
        len(
            list(
                swh_webhooks.sent_events_list_for_event_type(
                    origin_create_event_type.name, limit=limit
                )
            )
        )
        == limit
    )


@pytest.mark.parametrize(
    "for_endpoint", [False, True], ids=["for event type", "for endpoint"]
)
def test_list_sent_events_bad_parameters(
    swh_webhooks,
    origin_create_event_type,
    origin_create_endpoint1_no_channel,
    for_endpoint,
):
    swh_webhooks.event_type_create(origin_create_event_type)
    swh_webhooks.endpoint_create(origin_create_endpoint1_no_channel)

    before = after = datetime.now()

    with pytest.raises(
        ValueError,
        match="before and after parameters cannot be combined, only one can be provided",
    ):
        if for_endpoint:
            list(
                swh_webhooks.sent_events_list_for_endpoint(
                    origin_create_endpoint1_no_channel, before=before, after=after
                )
            )
        else:
            list(
                swh_webhooks.sent_events_list_for_event_type(
                    origin_create_event_type.name, before=before, after=after
                )
            )

    with pytest.raises(
        ValueError,
        match=f"Provided date {before.isoformat()} is not timezone aware",
    ):
        if for_endpoint:
            list(
                swh_webhooks.sent_events_list_for_endpoint(
                    origin_create_endpoint1_no_channel, before=before
                )
            )
        else:
            list(
                swh_webhooks.sent_events_list_for_event_type(
                    origin_create_event_type.name, after=after
                )
            )
