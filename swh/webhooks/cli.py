# Copyright (C) The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

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
def webhooks_event_type_group():
    pass
