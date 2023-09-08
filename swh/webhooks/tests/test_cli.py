# Copyright (C) 2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import os
import textwrap

import pytest

from swh.webhooks import EventType, Webhooks
from swh.webhooks.cli import webhooks_cli_group as cli


@pytest.fixture
def swh_webhooks(svix_server_url, svix_auth_token):
    return Webhooks(svix_server_url=svix_server_url, svix_auth_token=svix_auth_token)


def test_cli_missing_svix_token(cli_runner):
    result = cli_runner.invoke(cli, ["event-type"])
    assert result.exit_code != 0
    assert "Error: Svix authentication token is missing" in result.output


def test_cli_missing_svix_server_url(cli_runner, svix_auth_token):
    result = cli_runner.invoke(cli, ["--svix-token", svix_auth_token, "event-type"])
    assert result.exit_code != 0
    assert "Error: Svix server URL is missing" in result.output


def test_cli_svix_config_using_options(cli_runner, svix_server_url, svix_auth_token):
    result = cli_runner.invoke(
        cli,
        [
            "--svix-url",
            svix_server_url,
            "--svix-token",
            svix_auth_token,
            "event-type",
        ],
    )
    assert result.exit_code == 0


def test_cli_svix_config_using_envvars(
    cli_runner, monkeypatch, svix_server_url, svix_auth_token
):
    monkeypatch.setenv("SVIX_URL", svix_server_url)
    monkeypatch.setenv("SVIX_TOKEN", svix_auth_token)
    result = cli_runner.invoke(cli, ["event-type"])
    assert result.exit_code == 0


@pytest.fixture
def configfile_path(tmp_path, svix_server_url, svix_auth_token):
    configfile_path = os.path.join(tmp_path, "webhooks.yml")
    with open(configfile_path, "w") as configfile:
        configfile.write(
            textwrap.dedent(
                f"""
                webhooks:
                    svix:
                        server_url: {svix_server_url}
                        auth_token: {svix_auth_token}
                """
            )
        )
    return configfile_path


def test_cli_svix_config_using_configfile_option(cli_runner, configfile_path):
    result = cli_runner.invoke(cli, ["-C", configfile_path, "event-type"])
    assert result.exit_code == 0


def test_cli_svix_config_using_configfile_envvar(
    cli_runner, monkeypatch, configfile_path
):
    monkeypatch.setenv("SWH_CONFIG_FILENAME", configfile_path)
    result = cli_runner.invoke(cli, ["-C", configfile_path, "event-type"])
    assert result.exit_code == 0


@pytest.fixture
def add_event_type_cmd(datadir):
    return [
        "event-type",
        "add",
        "origin.create",
        "This event is triggered when a new software origin is added to the archive",
        os.path.join(datadir, "origin_create.json"),
    ]


@pytest.fixture
def valid_svix_credentials_options(svix_server_url, svix_auth_token):
    return ["-u", svix_server_url, "-t", svix_auth_token]


@pytest.fixture
def invalid_svix_credentials_options(svix_server_url):
    return ["-u", svix_server_url, "-t", "foo"]


def test_cli_add_event_type_auth_error(
    cli_runner, invalid_svix_credentials_options, add_event_type_cmd
):
    result = cli_runner.invoke(
        cli, invalid_svix_credentials_options + add_event_type_cmd
    )
    assert result.exit_code != 0

    assert (
        "Error: Svix server returned error 'authentication_failed' with detail 'Invalid token'"
        in result.output
    )


def test_cli_add_event_type(
    cli_runner, valid_svix_credentials_options, add_event_type_cmd, swh_webhooks
):
    result = cli_runner.invoke(cli, valid_svix_credentials_options + add_event_type_cmd)
    assert result.exit_code == 0

    assert swh_webhooks.event_type_get("origin.create")


def test_cli_get_event_type_auth_error(cli_runner, invalid_svix_credentials_options):
    result = cli_runner.invoke(
        cli,
        invalid_svix_credentials_options
        + [
            "event-type",
            "get",
            "origin.create",
        ],
    )
    assert result.exit_code != 0

    assert (
        "Error: Svix server returned error 'authentication_failed' with detail 'Invalid token'"
        in result.output
    )


def test_cli_get_event_type(
    cli_runner,
    valid_svix_credentials_options,
    swh_webhooks,
):
    event_type = EventType(
        name="origin.create",
        description="origin creation",
        schema={"type": "object"},
    )
    swh_webhooks.event_type_create(event_type)

    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "event-type",
            "get",
            "origin.create",
        ],
    )
    assert result.exit_code == 0
    assert f"{event_type.description}\n" in result.output
    assert '"type": "object"' in result.output

    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "event-type",
            "get",
            "--dump-schema",
            "origin.create",
        ],
    )
    assert result.output == '{"type": "object"}\n'


def test_cli_get_event_type_unknown(cli_runner, valid_svix_credentials_options):
    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "event-type",
            "get",
            "foo.bar",
        ],
    )
    assert result.exit_code != 0

    assert "Error: Event type foo.bar does not exist" in result.output
