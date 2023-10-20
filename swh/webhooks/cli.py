# Copyright (C) 2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import datetime
import json
import os
from pathlib import Path
import textwrap
from typing import List, Optional

import click

from swh.core.cli import CONTEXT_SETTINGS
from swh.core.cli import swh as swh_cli_group


@swh_cli_group.group(name="webhooks", context_settings=CONTEXT_SETTINGS)
@click.option(
    "--config-file",
    "-C",
    default=None,
    envvar="SWH_CONFIG_FILENAME",
    type=click.Path(
        exists=True,
        dir_okay=False,
    ),
    help="Configuration file.",
)
@click.option(
    "--svix-url",
    "-u",
    default=None,
    envvar="SVIX_URL",
    help=(
        "URL of the Svix server to use if not provided in configuration file "
        "(can also be provided in SVIX_URL environment variable)"
    ),
)
@click.option(
    "--svix-token",
    "-t",
    default=None,
    envvar="SVIX_TOKEN",
    help=(
        "Bearer token required to communicate with Svix REST API, used if not provided "
        "in configuration file (can also be provided in SVIX_TOKEN environment variable)"
    ),
)
@click.pass_context
def webhooks_cli_group(ctx, config_file, svix_url, svix_token):
    """Software Heritage Webhooks management built on top of the open-source framework Svix."""
    from swh.core import config

    ctx.ensure_object(dict)
    conf = config.read(config_file)
    ctx.obj["config"] = conf
    try:
        from swh.webhooks.interface import Webhooks

        webhooks = Webhooks(config_file, svix_url, svix_token)
    except Exception as e:
        ctx.fail(str(e))

    ctx.obj["webhooks"] = webhooks


@webhooks_cli_group.group("event-type")
def event_type():
    pass


@event_type.command("register-defaults")
@click.pass_context
def event_type_register_defaults(ctx):
    """Register default event types defined in swh-webhooks package."""
    from swh.webhooks.interface import EventType

    try:
        for root, _, files in os.walk(
            os.path.join(os.path.dirname(__file__), "event_types")
        ):
            for f in files:
                if not f.endswith(".json"):
                    continue
                with open(os.path.join(root, f), "r") as schema:
                    event_type_schema = json.load(schema)
                ctx.obj["webhooks"].event_type_create(
                    EventType(
                        name=event_type_schema["title"],
                        description=event_type_schema["description"],
                        schema=event_type_schema,
                    )
                )
    except Exception as e:
        ctx.fail(str(e))


@event_type.command("add")
@click.argument("name", nargs=1, required=True)
@click.argument("description", nargs=1, required=True)
@click.argument(
    "schema_file",
    nargs=1,
    required=True,
    type=click.Path(exists=True, dir_okay=False),
)
@click.pass_context
def event_type_add(ctx, name, description, schema_file):
    """Create or update a webhook event type.

    NAME must be a string in the form '<group>.<event>'.

    DESCRIPTION is a string giving info about the event type.

    SCHEMA_FILE is a path to a JSON schema file describing event payload.
    """
    from swh.webhooks.interface import EventType

    try:
        ctx.obj["webhooks"].event_type_create(
            EventType(
                name=name,
                description=description,
                schema=json.loads(Path(schema_file).read_text()),
            )
        )
    except Exception as e:
        ctx.fail(str(e))


@event_type.command("get")
@click.argument("name", nargs=1, required=True)
@click.option(
    "--dump-schema",
    "-d",
    is_flag=True,
    help=("Only dump raw JSON schema to stdout."),
)
@click.pass_context
def event_type_get(ctx, name, dump_schema):
    """Get info about a webhook event type.

    NAME must be a string in the form '<group>.<event>'.
    """
    try:
        event_type = ctx.obj["webhooks"].event_type_get(name)
        if dump_schema:
            click.echo(json.dumps(event_type.schema))
        else:
            click.echo(f"Description:\n  {event_type.description}\n")
            click.echo("JSON schema for payload:")
            click.echo(textwrap.indent(json.dumps(event_type.schema, indent=4), "  "))
    except Exception as e:
        ctx.fail(str(e))


@event_type.command("delete")
@click.argument("name", nargs=1, required=True)
@click.pass_context
def event_type_delete(ctx, name):
    """Delete a webhook event type.

    The event type is not removed from database but is archived, it is
    no longer listed and no more events of this type can be sent after
    this operation. It can be unarchived by creating it again.

    NAME must be a string in the form '<group>.<event>'.
    """
    try:
        ctx.obj["webhooks"].event_type_delete(name)
    except Exception as e:
        ctx.fail(str(e))


@event_type.command("list")
@click.pass_context
def event_type_list(ctx):
    """List webhook event types."""
    try:
        event_types = ctx.obj["webhooks"].event_types_list()
        if event_types:
            click.echo("Registered event types:\n")
            for event_type in event_types:
                click.echo(f"{event_type.name}:\n  {event_type.description}")
        else:
            click.echo("No event type registered")
    except Exception as e:
        ctx.fail(str(e))


@webhooks_cli_group.group("endpoint")
def endpoint():
    pass


@endpoint.command("create")
@click.argument("event-type-name", nargs=1, required=True)
@click.argument("url", nargs=1, required=True)
@click.option(
    "--channel",
    "-c",
    default=None,
    help=(
        "Optional channel the endpoint listens to. Channels are an extra "
        "dimension of filtering messages that is orthogonal to event types"
    ),
)
@click.option(
    "--secret",
    "-s",
    default=None,
    help=(
        "Optional secret used to verify authenticity of webhook messages, "
        "it is automatically generated or rotated otherwise"
    ),
)
@click.pass_context
def endpoint_create(ctx, event_type_name, url, channel, secret):
    """Create or update an endpoint to receive webhook messages of a specific event type.

    EVENT_TYPE_NAME must be a string in the form '<group>.<event>'.

    URL corresponds to the endpoint receiving webhook messages.
    """
    from swh.webhooks.interface import Endpoint

    try:
        ctx.obj["webhooks"].endpoint_create(
            Endpoint(url=url, event_type_name=event_type_name, channel=channel),
            secret=secret,
        )
    except Exception as e:
        ctx.fail(str(e))


@endpoint.command("get-secret")
@click.argument("event-type-name", nargs=1, required=True)
@click.argument("url", nargs=1, required=True)
@click.option(
    "--channel",
    "-c",
    default=None,
    help=(
        "Optional channel the endpoint listens to. Channels are an extra "
        "dimension of filtering messages that is orthogonal to event types"
    ),
)
@click.pass_context
def endpoint_get_secret(ctx, event_type_name, url, channel):
    """Get endpoint secret used to verify the authenticity of webhook messages.

    EVENT_TYPE_NAME must be a string in the form '<group>.<event>'.

    URL corresponds to the endpoint receiving webhook messages.
    """
    from swh.webhooks.interface import Endpoint

    try:
        click.echo(
            ctx.obj["webhooks"].endpoint_get_secret(
                Endpoint(url=url, event_type_name=event_type_name, channel=channel)
            )
        )
    except Exception as e:
        ctx.fail(str(e))


@endpoint.command("list")
@click.argument("event-type-name", nargs=1, required=True)
@click.option(
    "--ascending-order",
    "-a",
    is_flag=True,
    help=("List endpoints in the same order they were created"),
)
@click.option(
    "--limit",
    "-l",
    default=None,
    type=click.IntRange(min=1),
    help=("Maximum number of endpoints to list"),
)
@click.option(
    "--channel",
    "-c",
    default=None,
    help=(
        "List endpoints that will receive messages sent to the given channel. "
        "This includes endpoints not tied to any specific channel"
    ),
)
@click.pass_context
def endpoint_list(ctx, event_type_name, ascending_order, limit, channel):
    """List endpoint URLs for a specific event type.

    EVENT_TYPE_NAME must be a string in the form '<group>.<event>'.
    """
    try:
        for endpoint in ctx.obj["webhooks"].endpoints_list(
            event_type_name=event_type_name,
            channel=channel,
            ascending_order=ascending_order,
            limit=limit,
        ):
            click.echo(endpoint.url)

    except Exception as e:
        ctx.fail(str(e))


@endpoint.command("delete")
@click.argument("event-type-name", nargs=1, required=True)
@click.argument("url", nargs=1, required=True)
@click.option(
    "--channel",
    "-c",
    default=None,
    help=(
        "Optional channel the endpoint listens to. When endpoints are subscribed "
        "to a specific channel, they only receive messages for events addressed "
        "to this channel."
    ),
)
@click.pass_context
def endpoint_delete(ctx, event_type_name, url, channel):
    """Delete an endpoint receiving webhook messages of a specific event type.

    EVENT_TYPE_NAME must be a string in the form '<group>.<event>'.

    URL corresponds to the endpoint receiving webhook messages.
    """
    from swh.webhooks.interface import Endpoint

    try:
        ctx.obj["webhooks"].endpoint_delete(
            Endpoint(url=url, event_type_name=event_type_name, channel=channel)
        )
    except Exception as e:
        ctx.fail(str(e))


@webhooks_cli_group.group("event")
def event():
    pass


@event.command("send")
@click.argument("event-type-name", nargs=1, required=True)
@click.argument("payload-file", nargs=1, required=True, type=click.File("r"))
@click.option(
    "--channel",
    "-c",
    default=None,
    help=(
        "Optional channel endpoints might listen to. When endpoints are subscribed "
        "to a specific channel, they only receive messages for events addressed "
        "to this channel."
    ),
)
@click.pass_context
def event_send(ctx, event_type_name, payload_file, channel):
    """Send an event to endpoints listening a specific event type.

    EVENT_TYPE_NAME must be a string in the form '<group>.<event>'.

    PAYLOAD_FILE must be a path to a JSON file containing message payload
    or - if the payload should be read from standard input.
    """

    from jsonschema.exceptions import ValidationError

    try:
        ctx.obj["webhooks"].event_send(
            event_type_name=event_type_name,
            payload=json.load(payload_file),
            channel=channel,
        )
    except ValidationError as ve:
        error_message = "Payload validation against JSON schema failed\n\n" + str(ve)
        ctx.fail(error_message)
    except Exception as e:
        ctx.fail(str(e))


class EventListJSONEncoder(json.JSONEncoder):
    # Override the default method
    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)


@event.command("list")
@click.argument("event-type-name", nargs=1, required=True)
@click.option(
    "--endpoint-url",
    "-u",
    default=None,
    help=("List events sent to the given endpoint"),
)
@click.option(
    "--channel",
    "-c",
    default=None,
    help=("List events sent to the given channel"),
)
@click.option(
    "--before",
    "-b",
    default=None,
    # svix api only allows timezone aware datetime
    type=click.DateTime(formats=("%Y-%m-%dT%H:%M:%S.%f%z",)),
    help=("List events created before a specific timezone aware date"),
)
@click.option(
    "--after",
    "-a",
    default=None,
    # svix api only allows timezone aware datetime
    type=click.DateTime(formats=("%Y-%m-%dT%H:%M:%S.%f%z",)),
    help=("List events created after a specific timezone date"),
)
@click.option(
    "--limit",
    "-l",
    default=10,
    type=click.IntRange(min=1),
    help=("Maximum number of events to list"),
)
@click.pass_context
def event_list(ctx, event_type_name, endpoint_url, channel, before, after, limit):
    """List recent events sent to endpoints.

    It outputs a JSON list filled with events data.

    EVENT_TYPE_NAME must be a string in the form '<group>.<event>'.
    """
    from dataclasses import asdict

    from swh.webhooks.interface import Endpoint

    try:
        if endpoint_url:
            sent_events = ctx.obj["webhooks"].sent_events_list_for_endpoint(
                endpoint=Endpoint(endpoint_url, event_type_name, channel),
                limit=limit,
                before=before,
                after=after,
            )
        else:
            sent_events = ctx.obj["webhooks"].sent_events_list_for_event_type(
                event_type_name=event_type_name,
                channel=channel,
                limit=limit,
                before=before,
                after=after,
            )
        events = [asdict(event) for event in sent_events]
        click.echo(json.dumps(events, cls=EventListJSONEncoder, indent=4))
    except Exception as e:
        ctx.fail(str(e))


@webhooks_cli_group.command("journal-client")
@click.option(
    "--broker", "brokers", type=str, multiple=True, help="Kafka broker to connect to."
)
@click.option(
    "--prefix", type=str, default=None, help="Prefix of Kafka topic names to read from."
)
@click.option("--group-id", type=str, help="Consumer/group id for reading from Kafka.")
@click.option(
    "--stop-after-objects",
    "-m",
    default=None,
    type=int,
    help="Maximum number of objects to replay. Default is to run forever.",
)
@click.option(
    "--batch-size",
    "-b",
    default=200,
    type=int,
    help="Maximum number of kafka messages by batch. Default is 200.",
)
@click.pass_context
def journal_client(
    ctx,
    brokers: List[str],
    prefix: str,
    group_id: str,
    stop_after_objects: Optional[int],
    batch_size: Optional[int],
):
    from swh.journal.client import get_journal_client
    from swh.webhooks.journal_client import process

    cfg = ctx.obj["config"]
    journal_cfg = cfg.get("journal", {})

    if brokers:
        journal_cfg["brokers"] = brokers
    if not journal_cfg.get("brokers"):
        raise ValueError("The brokers configuration is mandatory.")

    if prefix:
        journal_cfg["prefix"] = prefix
    if group_id:
        journal_cfg["group_id"] = group_id

    if stop_after_objects:
        journal_cfg["stop_after_objects"] = stop_after_objects
    if batch_size:
        journal_cfg["batch_size"] = batch_size

    client = get_journal_client(
        cls="kafka",
        **journal_cfg,
    )

    webhooks = ctx.obj["webhooks"]

    try:
        process(client, webhooks)
    except KeyboardInterrupt:
        ctx.exit(0)
    else:
        print("Done.")
    finally:
        client.close()
