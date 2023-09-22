# Copyright (C) The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import json
from pathlib import Path
import textwrap

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

    ctx.ensure_object(dict)
    try:
        from swh.webhooks.interface import Webhooks

        webhooks = Webhooks(config_file, svix_url, svix_token)
    except Exception as e:
        ctx.fail(str(e))

    ctx.obj["webhooks"] = webhooks


@webhooks_cli_group.group("event-type")
def event_type():
    pass


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
@click.pass_context
def endpoint_create(ctx, event_type_name, url, channel):
    """Create an endpoint to receive webhook messages of a specific event type.

    That operation is idempotent.

    EVENT_TYPE_NAME must be a string in the form '<group>.<event>'.

    URL corresponds to the endpoint receiving webhook messages.
    """
    from swh.webhooks.interface import Endpoint

    try:
        ctx.obj["webhooks"].endpoint_create(
            Endpoint(url=url, event_type_name=event_type_name, channel=channel)
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
