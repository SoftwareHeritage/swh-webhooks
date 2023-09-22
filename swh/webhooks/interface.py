# Copyright (C) 2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
import re
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Protocol,
    Tuple,
    TypeVar,
    Union,
)
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
    ListResponseEndpointMessageOut,
    ListResponseEndpointOut,
    ListResponseEventTypeOut,
    ListResponseMessageAttemptOut,
    MessageAttemptListOptions,
    MessageIn,
    Ordering,
    Svix,
    SvixOptions,
)
from svix.exceptions import HttpError
from svix.internal.openapi_client.types import Unset
from svix.webhooks import Webhook

from swh.core.config import load_from_envvar, read_raw_config


def _svix_api(
    svix_config: Dict[str, Any],
    server_url: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> Svix:
    svix_auth_token = svix_config.get("auth_token", auth_token or "")
    if not svix_auth_token:
        raise ValueError("Svix authentication token is missing")
    svix_server_url = svix_config.get("server_url", server_url or "")
    if not svix_server_url:
        raise ValueError("Svix server URL is missing")
    return Svix(
        svix_auth_token,
        SvixOptions(server_url=svix_server_url),
    )


def _gen_uuid(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))


def _get_app_name_and_uid(event_type_name: str) -> Tuple[str, str]:
    return event_type_name, _gen_uuid(event_type_name)


def get_config(config_file: Optional[str] = None) -> Dict[str, Any]:
    """Read the configuration file ``config_file``.

    If an environment variable ``SWH_CONFIG_FILENAME`` is defined, this
    takes precedence over the ``config_file`` parameter.

    """
    webhooks_config = {}
    config_filename = os.environ.get("SWH_CONFIG_FILENAME")
    if config_filename:
        webhooks_config.update(load_from_envvar())
    elif config_file:
        webhooks_config.update(read_raw_config(config_file))
    return webhooks_config.get("webhooks", {})


SvixData = TypeVar("SvixData")
SvixListIterator = Optional[str]


class SvixListResponse(Protocol[SvixData]):
    data: List[SvixData]
    iterator: Union[Unset, None, str]
    done: bool


def svix_list(
    svix_list_request: Callable[[SvixListIterator], SvixListResponse[SvixData]]
) -> Iterator[SvixData]:
    iterator = None
    while True:
        response = svix_list_request(iterator)
        yield from response.data
        iterator = response.iterator
        if response.done:
            break


class SvixHttpError(Exception):
    def __init__(self, error_dict: Dict[str, str]):
        self.error_code = error_dict.get("code", "")
        self.error_detail = error_dict.get("detail", "")

    def __str__(self) -> str:
        return (
            f"Svix server returned error '{self.error_code}' "
            f"with detail '{self.error_detail}'."
        )


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
class SentEvent:
    """Webhook event delivery attempt definition"""

    event_type_name: str
    """The type of sent event"""
    endpoint_url: str
    """The URL of the targeted endpoint"""
    channel: Optional[str]
    """The channel associated to the endpoint"""
    headers: Dict[str, Any]
    """HTTP headers sent with POST request"""
    msg_id: str
    """Internal message identifier"""
    payload: Dict[str, Any]
    """JSON payload sent as POST request body"""
    timestamp: datetime
    """The date the request was sent"""
    response: str
    """The response sent by the endpoint"""
    response_status_code: int
    """The status code of the sent POST request"""


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
        config_file: Optional[str] = None,
        svix_server_url: Optional[str] = None,
        svix_auth_token: Optional[str] = None,
    ):
        self.config = get_config(config_file)
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

        try:
            self.svix_api.application.get_or_create(
                ApplicationIn(name=app_name, uid=app_uid)
            )
            self.svix_api.event_type.create(
                EventTypeIn(
                    name=event_type.name,
                    description=event_type.description,
                    schemas={"1": event_type.schema},
                )
            )
        except HttpError as http_error:
            error_dict = http_error.to_dict()
            if error_dict["code"] == "event_type_exists":
                self.svix_api.event_type.update(
                    event_type.name,
                    EventTypeUpdate(
                        description=event_type.description,
                        schemas={"1": event_type.schema},
                    ),
                )
            else:
                raise SvixHttpError(error_dict)

    def event_type_get(self, event_type_name) -> EventType:
        """Get an active event type by its name.

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

            if event_type.archived:
                raise ValueError(f"Event type {event_type_name} is archived")

            return EventType(
                name=event_type.name,
                description=event_type.description,
                schema=event_type.schemas.get("1"),  # type: ignore
            )
        except HttpError as http_error:
            error_dict = http_error.to_dict()
            if error_dict["code"] == "not_found":
                raise ValueError(f"Event type {event_type_name} does not exist")
            else:
                raise SvixHttpError(error_dict)

    def event_types_list(self) -> List[EventType]:
        """List all registered and active event types.

        Raises:
            svix.exceptions.HTTPError: if a request to the Svix REST API fails

        Returns:
            A list of all registered event types.
        """

        def list_event_type(iterator: SvixListIterator) -> ListResponseEventTypeOut:
            return self.svix_api.event_type.list(
                EventTypeListOptions(with_content=True, iterator=iterator)
            )

        event_types = []
        for event_type in svix_list(list_event_type):
            event_types.append(
                EventType(
                    name=event_type.name,
                    description=event_type.description,
                    schema=event_type.schemas.get("1"),  # type: ignore
                )
            )
        return event_types

    def event_type_delete(self, event_type_name) -> None:
        """Delete an event type.

        The event type is not removed from database but is archived, it is
        no longer listed and no more events of this type can be sent after
        this operation. It can be unarchived by creating it again.

        Args:
            event_type_name: The name of the event type to delete

        Raises:
            ValueError: if there is no event type with this name
            svix.exceptions.HTTPError: if a request to the Svix REST API fails
        """
        try:
            self.svix_api.event_type.delete(event_type_name)
        except HttpError as http_error:
            error_dict = http_error.to_dict()
            if error_dict["code"] == "not_found":
                raise ValueError(f"Event type {event_type_name} does not exist")
            else:
                raise SvixHttpError(error_dict)

    def endpoint_create(self, endpoint: Endpoint) -> None:
        """Create an endpoint to receive webhook messages.

        That operation is idempotent.

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
            error_dict = http_error.to_dict()
            if error_dict["code"] != "conflict":
                raise SvixHttpError(error_dict)

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
        # check event type exists
        self.event_type_get(event_type_name)
        _, app_uid = _get_app_name_and_uid(event_type_name)

        def list_endpoint(iterator: SvixListIterator) -> ListResponseEndpointOut:
            return self.svix_api.endpoint.list(
                app_uid,
                EndpointListOptions(
                    iterator=iterator,
                    order=Ordering.ASCENDING
                    if ascending_order
                    else Ordering.DESCENDING,
                ),
            )

        nb_listed_endpoints = 0

        for endpoint in svix_list(list_endpoint):
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

    def sent_events_list(
        self,
        endpoint: Endpoint,
        before: Optional[datetime] = None,
        after: Optional[datetime] = None,
    ) -> Iterator[SentEvent]:
        """List recent events sent to an endpoint.

        Args:
            endpoint: the endpoint to list sent events
            before: list sent events before that date if provided
            after: list sent events after that date if provided

        Returns:
            list of sent events

        Raises:
            ValueError: if the endpoint does not exist
            svix.exceptions.HTTPError: if a request to the Svix REST API fails
        """

        endpoint_secret = self.endpoint_get_secret(endpoint)

        webhook = Webhook(endpoint_secret)

        _, app_uid = _get_app_name_and_uid(endpoint.event_type_name)
        endpoint_uid = endpoint.uid

        message_data = {}

        def list_attempted_messages(
            iterator: SvixListIterator,
        ) -> ListResponseEndpointMessageOut:
            return self.svix_api.message_attempt.list_attempted_messages(
                app_uid,
                endpoint_uid,
                MessageAttemptListOptions(
                    iterator=iterator, before=before, after=after
                ),
            )

        message_data.update(
            {
                message.id: {
                    "payload": message.payload,
                    "channels": message.channels,
                }
                for message in svix_list(list_attempted_messages)
            }
        )

        def list_attempted_messages_by_endpoint(
            iterator: SvixListIterator,
        ) -> ListResponseMessageAttemptOut:
            return self.svix_api.message_attempt.list_by_endpoint(
                app_uid,
                endpoint_uid,
                MessageAttemptListOptions(
                    iterator=iterator, before=before, after=after
                ),
            )

        for attempt in svix_list(list_attempted_messages_by_endpoint):
            payload = message_data.get(attempt.msg_id, {}).get("payload", {})
            assert isinstance(payload, dict)
            channels = message_data.get(attempt.msg_id, {}).get("channels")
            json_payload = json.dumps(payload, separators=(",", ":"))
            yield SentEvent(
                event_type_name=endpoint.event_type_name,
                channel=endpoint.channel if isinstance(channels, list) else None,
                endpoint_url=attempt.url,
                headers={
                    "Content-Length": str(len(json_payload)),
                    "Content-Type": "application/json",
                    "Webhook-Id": attempt.msg_id,
                    "Webhook-Timestamp": str(int(attempt.timestamp.timestamp())),
                    "Webhook-Signature": webhook.sign(
                        attempt.msg_id,
                        attempt.timestamp,
                        json_payload,
                    ),
                    "X-Swh-Event": endpoint.event_type_name,
                },
                msg_id=attempt.msg_id,
                payload=payload if payload is not None else {},
                timestamp=attempt.timestamp,
                response=attempt.response,
                response_status_code=attempt.response_status_code,
            )