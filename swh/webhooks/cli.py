# Copyright (C) The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import json
from pathlib import Path

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
        from swh.webhooks import Webhooks

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
    from swh.webhooks import EventType

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
