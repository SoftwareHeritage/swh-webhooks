# Copyright (C) 2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import re
import shutil

from jsonschema.exceptions import SchemaError
import pytest

from swh.webhooks import Endpoint, EventType, Webhooks

if shutil.which("docker") is None:
    pytest.skip("skipping tests as docker command is missing", allow_module_level=True)


@pytest.fixture
def swh_webhooks():
    return Webhooks()


@pytest.fixture
def origin_create_event_type():
    return EventType(
        name="origin.create",
        description=(
            "This event is triggered when a new software origin is added to the archive"
        ),
        schema={
            "type": "object",
            "properties": {
                "origin_url": {
                    "type": "string",
                    "description": "The URL of the newly created software origin",
                    "format": "iri",
                },
            },
            "required": ["origin_url"],
        },
    )


@pytest.fixture
def origin_visit_event_type():
    return EventType(
        name="origin.visit",
        description=(
            "This event is triggered when a new visit of a software origin was performed"
        ),
        schema={
            "type": "object",
            "properties": {
                "origin_url": {
                    "type": "string",
                    "description": "The URL of the visited software origin",
                    "format": "iri",
                },
                "visit_type": {
                    "type": "string",
                    "description": "The type of visit performed",
                },
                "visit_date": {
                    "type": "string",
                    "format": "date-time",
                    "description": "The date the visit was performed",
                },
                "visit_status": {
                    "type": "string",
                    "enum": [
                        "created",
                        "ongoing",
                        "full",
                        "partial",
                        "not_found",
                        "failed",
                    ],
                    "description": "The status of the visit",
                },
                "snapshot_swhid": {
                    "type": ["string", "null"],
                    "pattern": "^swh:[0-9]:[0-9a-f]{40}$",
                },
            },
            "required": [
                "origin_url",
                "visit_type",
                "visit_date",
                "visit_status",
                "snapshot_swhid",
            ],
        },
    )


FIRST_GIT_ORIGIN_URL = "https://git.example.org/user/project"
SECOND_GIT_ORIGIN_URL = "https://git.example.org/user/project2"


@pytest.fixture
def origin_create_endpoint1_no_channel(origin_create_event_type):
    return Endpoint(
        url="https://example.org/webhook/origin/created",
        event_type_name=origin_create_event_type.name,
    )


@pytest.fixture
def origin_create_endpoint2_no_channel(origin_create_event_type):
    return Endpoint(
        url="https://example.org/webhook/origin/created/other",
        event_type_name=origin_create_event_type.name,
    )


@pytest.fixture
def origin_visit_endpoint1_channel1(origin_visit_event_type):
    return Endpoint(
        url="https://example.org/webhook/origin/visited",
        event_type_name=origin_visit_event_type.name,
        channel=FIRST_GIT_ORIGIN_URL,
    )


@pytest.fixture
def origin_visit_endpoint2_channel2(origin_visit_event_type):
    return Endpoint(
        url="https://example.org/webhook/origin/visited/other",
        event_type_name=origin_visit_event_type.name,
        channel=SECOND_GIT_ORIGIN_URL,
    )


@pytest.fixture
def origin_visit_endpoint3_no_channel(origin_visit_event_type):
    return Endpoint(
        url="https://example.org/webhook/origin/visited/another",
        event_type_name=origin_visit_event_type.name,
    )


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

    assert swh_webhooks.endpoint_get_secret(origin_create_endpoint1_no_channel)

    assert swh_webhooks.endpoint_get_secret(origin_visit_endpoint1_channel1)


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
    with pytest.raises(
        ValueError, match=re.escape(f"{unknown_endpoint} does not exist")
    ):
        swh_webhooks.endpoint_get_secret(unknown_endpoint)

    with pytest.raises(
        ValueError, match=re.escape(f"{unknown_endpoint} does not exist")
    ):
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
