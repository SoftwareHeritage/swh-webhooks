# Copyright (C) The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import click

from swh.core.cli import CONTEXT_SETTINGS
from swh.core.cli import swh as swh_cli_group


@swh_cli_group.group(name="webhooks", context_settings=CONTEXT_SETTINGS)
@click.pass_context
def webhooks_cli_group(ctx):
    """Webhooks main command."""
