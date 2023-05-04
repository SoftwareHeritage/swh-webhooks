# Copyright (C) 2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from dataclasses import dataclass, field
from datetime import datetime
import os
import re
from typing import Any, Dict, Iterator, List, Optional, Tuple
import uuid

import jsonschema
from jsonschema.validators import Draft7Validator
from svix.api import (
    ApplicationIn,
    EndpointHeadersIn,
    EndpointIn,
    EndpointListOptions,
    EventTypeIn,
    EventTypeListOptions,
    EventTypeUpdate,
    MessageIn,
    Ordering,
    Svix,
    SvixOptions,
)
from svix.exceptions import HttpError

from swh.core.config import load_named_config

_webhooks_config: Dict[str, Any] = {}


def _svix_api(
    svix_config: Dict[str, Any],
    server_url: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> Svix:
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
    return _webhooks_config.get("webhooks", {})


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


@dataclass
class Endpoint:
    """Webhook user endpoint definition"""

    url: str
    """URL of the endpoint to receive webhook messages"""
    event_type_name: str
    """The type of event the endpoint receives"""
    channel: Optional[str] = None
    """Optional channel this endpoint listens to, channels are an extra
    dimension of filtering messages that is orthogonal to event types"""
    metadata: Dict[str, Any] = field(default_factory=dict)
    """Optional metadata associated to the endpoint"""

    @property
    def uid(self):
        """Unique identifier for the endpoint"""
        return _gen_uuid(f"{self.event_type_name}-{self.url}-{self.channel}")


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
        self.config = get_config()
        self.svix_api = _svix_api(
            self.config.get("svix", {}), svix_server_url, svix_auth_token
        )

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

    def endpoint_create(self, endpoint: Endpoint) -> None:
        """Create an endpoint to receive webhook messages.

        Args:
            endpoint: the endpoint to create

        Raises:
            ValueError: if the event type associated to the endpoint does not exist
            svix.exceptions.HTTPError: if a request to the Svix REST API fails
        """
        self.event_type_get(endpoint.event_type_name)

        _, app_uid = _get_app_name_and_uid(endpoint.event_type_name)
        endpoint_uid = endpoint.uid

        metadata = dict(endpoint.metadata)
        channel = None
        if endpoint.channel is not None:
            # Svix channel names are limited to 128 characters and must be matched by
            # the following regular expression: ^[a-zA-Z0-9\-_.]+$, so we use their UUID5
            # values instead and store the names mapping in the endpoint metadata
            channel = _gen_uuid(endpoint.channel)
            metadata[channel] = endpoint.channel

        try:
            self.svix_api.endpoint.create(
                app_uid,
                EndpointIn(
                    url=endpoint.url,
                    uid=endpoint_uid,
                    version=1,
                    filter_types=[endpoint.event_type_name],
                    channels=[channel] if channel else None,
                    metadata=metadata,
                ),
            )
        except HttpError as http_error:
            if http_error.to_dict()["code"] != "conflict":
                raise

        # Add SWH event type name in webhook POST request headers
        self.svix_api.endpoint.update_headers(
            app_uid,
            endpoint_uid,
            EndpointHeadersIn(headers={"X-Swh-Event": endpoint.event_type_name}),
        )

    def endpoints_list(
        self,
        event_type_name: str,
        channel: Optional[str] = None,
        ascending_order: bool = False,
        limit: Optional[int] = None,
    ) -> Iterator[Endpoint]:
        """List all endpoints receiving messages for a given event type.

        Args:
            event_type_name: the name of the event type to retrieve associated endpoints
            channel: optional channel name, only endpoints listening to it are listed
                if provided, please not that endpoints not listening to any channel receive
                all events and are always listed
            ascending_order: whether to retrieve endpoints in the order they were created
            limit: maximum number of endpoints to list

        Yields:
            Endpoints listening to the event type

        Raises:
            ValueError: if the event type does not exist
            svix.exceptions.HTTPError: if a request to the Svix REST API fails

        """
        self.event_type_get(event_type_name)
        _, app_uid = _get_app_name_and_uid(event_type_name)

        iterator = None
        nb_listed_endpoints = 0
        while True:
            endpoints_out = self.svix_api.endpoint.list(
                app_uid,
                EndpointListOptions(
                    iterator=iterator,
                    order=Ordering.ASCENDING
                    if ascending_order
                    else Ordering.DESCENDING,
                ),
            )
            for endpoint in endpoints_out.data:
                filter_types = endpoint.filter_types
                assert isinstance(filter_types, list)
                if event_type_name in filter_types:
                    metadata = endpoint.metadata
                    assert isinstance(metadata, dict)
                    channels_in = endpoint.channels
                    channel_out = None
                    if channels_in is not None and isinstance(channels_in, list):
                        channel_out = endpoint.metadata.pop(channels_in[0])
                    if channel_out is None or channel_out == channel:
                        nb_listed_endpoints += 1
                        yield Endpoint(
                            url=endpoint.url,
                            event_type_name=event_type_name,
                            channel=channel_out,
                            metadata=metadata,
                        )
                        if limit and nb_listed_endpoints == limit:
                            break

            iterator = endpoints_out.iterator

            if endpoints_out.done or (limit and nb_listed_endpoints == limit):
                break

    def endpoint_get_secret(self, endpoint: Endpoint) -> str:
        """Get secret for given endpoint to verify webhook signatures.

        Args:
            endpoint: The endpoint to retrieve the secret

        Returns:
            The endpoint's secret.

        Raises:
            ValueError: if the endpoint does not exist
            svix.exceptions.HTTPError: if a request to the Svix REST API fails
        """
        _, app_uid = _get_app_name_and_uid(endpoint.event_type_name)
        endpoint_uid = endpoint.uid
        try:
            secret_out = self.svix_api.endpoint.get_secret(app_uid, endpoint_uid)
        except HttpError as http_error:
            if http_error.to_dict()["code"] == "not_found":
                raise ValueError(f"{endpoint} does not exist")
            else:
                raise
        return secret_out.key

    def endpoint_delete(self, endpoint: Endpoint) -> None:
        """Delete an endpoint.

        Args:
            endpoint: The endpoint to delete

        Raises:
            ValueError: if the endpoint does not exist
            svix.exceptions.HTTPError: if a request to the Svix REST API fails
        """
        self.event_type_get(endpoint.event_type_name)
        _, app_uid = _get_app_name_and_uid(endpoint.event_type_name)
        try:
            self.svix_api.endpoint.delete(app_uid, endpoint.uid)
        except HttpError as http_error:
            if http_error.to_dict()["code"] == "not_found":
                raise ValueError(f"{endpoint} does not exist")

    def event_send(
        self,
        event_type_name: str,
        payload: Dict[str, Any],
        channel: Optional[str] = None,
    ) -> Optional[Tuple[str, datetime]]:
        """Send an event to registered endpoints.

        Args:
            event_type_name: the name of the event type to send
            payload: JSON payload of the event
            channel: optional channel name, channels are case-sensitive,
                and endpoints that are filtering for a specific channel will only
                get messages sent to that specific channel.

        Returns:
            Sent message id and timestamp as a tuple or :const:`None` if no endpoints
            are listening to the event type.

        Raises:
            ValueError: if the event type does not exist
            jsonschema.exceptions.ValidationError: if the payload does not match the
                event schema
            svix.exceptions.HTTPError: if a request to the Svix REST API fails
        """
        event_type = self.event_type_get(event_type_name)

        jsonschema.validate(payload, event_type.schema)

        _, app_uid = _get_app_name_and_uid(event_type_name)
        message_out = self.svix_api.message.create(
            app_uid,
            MessageIn(
                event_type=event_type_name,
                payload=payload,
                channels=[_gen_uuid(channel)] if channel else None,
                payload_retention_period=self.config.get("event_retention_period", 90),
            ),
        )

        return message_out.id, message_out.timestamp
