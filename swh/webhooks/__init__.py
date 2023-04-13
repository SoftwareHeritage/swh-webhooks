# Copyright (C) 2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from dataclasses import dataclass
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid

from jsonschema.validators import Draft7Validator
from svix.api import (
    ApplicationIn,
    EventTypeIn,
    EventTypeListOptions,
    EventTypeUpdate,
    Svix,
    SvixOptions,
)
from svix.exceptions import HttpError

from swh.core.config import load_named_config

_webhooks_config: Dict[str, Any] = {}


def _svix_api(
    server_url: Optional[str] = None, auth_token: Optional[str] = None
) -> Svix:
    svix_config = get_config().get("webhooks", {}).get("svix", {})
    return Svix(
        svix_config.get("auth_token", auth_token or ""),
        SvixOptions(server_url=svix_config.get("server_url", server_url or "")),
    )


def _gen_uuid(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))


def _get_app_name_and_uid(event_type_name: str) -> Tuple[str, str]:
    return event_type_name, _gen_uuid(event_type_name)


def get_config(config_file: str = "webhooks") -> Dict[str, Any]:
    """Read the configuration file ``config_file``.

    If an environment variable ``SWH_CONFIG_FILENAME`` is defined, this
    takes precedence over the ``config_file`` parameter.

    """
    if not _webhooks_config:
        config_filename = os.environ.get("SWH_CONFIG_FILENAME")
        if config_filename:
            config_file = config_filename
        _webhooks_config.update(load_named_config(config_file))
    return _webhooks_config


@dataclass
class EventType:
    """Webhook event type definition

    An event type is defined by a name, a description and a
    `JSON schema <https://json-schema.org/>`__.
    """

    name: str
    """name of the event type, in the form ``<group>.<event>``"""
    description: str
    """description of the event type"""
    schema: Dict[str, Any]
    """JSON schema describing the payload sent when the event is triggered"""


class Webhooks:
    """Interface for Software Heritage Webhooks management built on
    top of the Svix framework (https://docs.svix.com/).

    Svix makes sending webhooks easy and reliable by offering webhook
    sending as a service.

    Args:
        svix_server_url: optional URL of the Svix server, retrieved from
            configuration if not provided
        svix_auth_token: optional bearer token used to perform authenticated
            requests to the Svix REST API, retrieved from configuration if
            not provided
    """

    def __init__(
        self,
        svix_server_url: Optional[str] = None,
        svix_auth_token: Optional[str] = None,
    ):
        self.svix_api = _svix_api(svix_server_url, svix_auth_token)

    def event_type_create(self, event_type: EventType) -> None:
        """Create or update a webhook event type.

        Args:
            event_type: The event type to create or update

        Raises:
            ValueError: if the event type name is not valid
            svix.exceptions.HTTPError: if a request to the Svix REST API fails
            jsonschema.exceptions.SchemaError: if the JSON schema of the event type is not valid
        """
        if not re.match(r"^[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+$", event_type.name):
            raise ValueError("Event type name must be in the form '<group>.<event>'")

        # Svix uses draft 7 of JSON schema
        Draft7Validator.check_schema(event_type.schema)

        # we create one svix application per event type that gathers
        # all endpoints receiving it
        app_name, app_uid = _get_app_name_and_uid(event_type.name)
        self.svix_api.application.get_or_create(
            ApplicationIn(name=app_name, uid=app_uid)
        )

        try:
            self.svix_api.event_type.create(
                EventTypeIn(
                    name=event_type.name,
                    description=event_type.description,
                    schemas={"1": event_type.schema},
                )
            )
        except HttpError as http_error:
            if http_error.to_dict()["code"] == "event_type_exists":
                self.svix_api.event_type.update(
                    event_type.name,
                    EventTypeUpdate(
                        description=event_type.description,
                        schemas={"1": event_type.schema},
                    ),
                )
            else:
                raise

    def event_type_get(self, event_type_name) -> EventType:
        """Get an event type by its name.

        Args:
            event_type_name: The name of the event type to retrieve

        Raises:
            ValueError: if there is no event type with this name
            svix.exceptions.HTTPError: if a request to the Svix REST API fails

        Returns:
            The requested event type.

        """
        try:
            event_type = self.svix_api.event_type.get(event_type_name)

            return EventType(
                name=event_type.name,
                description=event_type.description,
                schema=event_type.schemas.get("1"),  # type: ignore
            )
        except HttpError as http_error:
            if http_error.to_dict()["code"] == "not_found":
                raise ValueError(f"Event type {event_type_name} does not exist")
            else:
                raise

    def event_types_list(self) -> List[EventType]:
        """List all registered event types.

        Raises:
            svix.exceptions.HTTPError: if a request to the Svix REST API fails

        Returns:
            A list of all registered event types.
        """
        iterator = None
        event_types = []
        while True:
            event_types_out = self.svix_api.event_type.list(
                EventTypeListOptions(with_content=True, iterator=iterator)
            )
            event_types += [
                EventType(
                    name=event_type.name,
                    description=event_type.description,
                    schema=event_type.schemas.get("1"),  # type: ignore
                )
                for event_type in event_types_out.data
            ]
            iterator = event_types_out.iterator
            if event_types_out.done:
                break
        return event_types

    def event_type_delete(self, event_type_name) -> None:
        """Delete an event type.

        Args:
            event_type_name: The name of the event type to delete

        Raises:
            ValueError: if there is no event type with this name
            svix.exceptions.HTTPError: if a request to the Svix REST API fails
        """
        try:
            self.svix_api.event_type.delete(event_type_name)
        except HttpError as http_error:
            if http_error.to_dict()["code"] == "not_found":
                raise ValueError(f"Event type {event_type_name} does not exist")
            else:
                raise
