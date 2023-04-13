# Copyright (C) 2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import shutil

from jsonschema.exceptions import SchemaError
import pytest

from swh.webhooks import EventType, Webhooks

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
