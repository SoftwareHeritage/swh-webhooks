# Copyright (C) 2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import os
import textwrap

import pytest

from swh.webhooks.cli import webhooks_cli_group as cli


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
