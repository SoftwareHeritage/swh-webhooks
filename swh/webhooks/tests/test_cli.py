# Copyright (C) 2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information


import json
import os
from pathlib import Path
import textwrap

import pytest

from swh.webhooks.cli import webhooks_cli_group as cli
from swh.webhooks.interface import Endpoint, EventType, Webhooks


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


def test_cli_delete_event_type_auth_error(cli_runner, invalid_svix_credentials_options):
    result = cli_runner.invoke(
        cli,
        invalid_svix_credentials_options
        + [
            "event-type",
            "delete",
            "origin.create",
        ],
    )
    assert result.exit_code != 0

    assert (
        "Error: Svix server returned error 'authentication_failed' with detail 'Invalid token'"
        in result.output
    )


def test_cli_delete_unknown_event_type(cli_runner, valid_svix_credentials_options):
    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "event-type",
            "delete",
            "foo",
        ],
    )
    assert result.exit_code != 0

    assert "Error: Event type foo does not exist" in result.output


def test_cli_delete_event_type(
    cli_runner, valid_svix_credentials_options, swh_webhooks
):
    event_type = EventType(
        name="origin.create",
        description="origin creation",
        schema={"type": "object"},
    )
    swh_webhooks.event_type_create(event_type)

    assert swh_webhooks.event_type_get("origin.create")

    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "event-type",
            "delete",
            "origin.create",
        ],
    )
    assert result.exit_code == 0

    with pytest.raises(ValueError, match="Event type origin.create is archived"):
        swh_webhooks.event_type_get("origin.create")


def test_cli_create_endpoint_auth_error(cli_runner, invalid_svix_credentials_options):
    result = cli_runner.invoke(
        cli,
        invalid_svix_credentials_options
        + [
            "endpoint",
            "create",
            "origin.create",
            "https://example.org/webhook",
        ],
    )
    assert result.exit_code != 0

    assert (
        "Error: Svix server returned error 'authentication_failed' with detail 'Invalid token'"
        in result.output
    )


def test_cli_create_endpoint_unknown_event_type(
    cli_runner, valid_svix_credentials_options
):
    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "endpoint",
            "create",
            "origin.create",
            "https://example.org/webhook",
        ],
    )
    assert result.exit_code != 0

    assert "Error: Event type origin.create does not exist" in result.output


@pytest.mark.parametrize("with_channel", [False, True])
def test_cli_create_endpoint(
    cli_runner, valid_svix_credentials_options, swh_webhooks, with_channel
):
    event_type_name = "origin.create"
    url = "https://example.org/webhook"
    channel = "foo" if with_channel else None

    event_type = EventType(
        name=event_type_name,
        description="origin creation",
        schema={"type": "object"},
    )
    swh_webhooks.event_type_create(event_type)

    cmd = [
        "endpoint",
        "create",
        event_type_name,
        url,
    ]
    if with_channel:
        cmd += [
            "--channel",
            channel,
        ]

    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options + cmd,
    )
    assert result.exit_code == 0

    endpoints = list(
        swh_webhooks.endpoints_list(event_type_name=event_type_name, channel=channel)
    )

    assert endpoints
    assert endpoints[0].event_type_name == event_type_name
    assert endpoints[0].url == url
    assert endpoints[0].channel == channel

    # check same command call does not terminate with error
    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options + cmd,
    )
    assert result.exit_code == 0


def test_cli_list_endpoints_auth_error(cli_runner, invalid_svix_credentials_options):
    result = cli_runner.invoke(
        cli,
        invalid_svix_credentials_options
        + [
            "endpoint",
            "list",
            "origin.create",
        ],
    )
    assert result.exit_code != 0

    assert (
        "Error: Svix server returned error 'authentication_failed' with detail 'Invalid token'"
        in result.output
    )


def test_cli_list_endpoints_unknown_event_type(
    cli_runner, valid_svix_credentials_options
):
    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "endpoint",
            "list",
            "foo",
        ],
    )
    assert result.exit_code != 0

    assert "Error: Event type foo does not exist" in result.output


@pytest.mark.parametrize("limit", [None, 5, 10, 15])
def test_cli_list_endpoints(
    cli_runner, valid_svix_credentials_options, swh_webhooks, limit
):
    event_type_name = "origin.create"
    event_type = EventType(
        name=event_type_name,
        description="origin creation",
        schema={"type": "object"},
    )
    swh_webhooks.event_type_create(event_type)

    endpoint_urls = []
    for i in range(10):
        endpoint_url = f"https://example.org/webhook/{i}"
        swh_webhooks.endpoint_create(
            Endpoint(url=endpoint_url, event_type_name=event_type_name)
        )
        endpoint_urls.append(endpoint_url)

    cmd = [
        "endpoint",
        "list",
        event_type_name,
    ]
    if limit:
        cmd += [
            "--limit",
            limit,
        ]

    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options + cmd,
    )
    assert result.exit_code == 0

    assert "\n".join(list(reversed(endpoint_urls))[:limit]) in result.output

    cmd.append("--ascending-order")

    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options + cmd,
    )
    assert result.exit_code == 0

    assert "\n".join(endpoint_urls[:limit]) in result.output


def test_cli_list_endpoints_with_channels(
    cli_runner, valid_svix_credentials_options, swh_webhooks
):
    event_type_name = "origin.create"
    event_type = EventType(
        name=event_type_name,
        description="origin creation",
        schema={"type": "object"},
    )
    swh_webhooks.event_type_create(event_type)

    endpoint_foo_channel_urls = []
    endpoint_bar_channel_urls = []
    for i in range(10):
        endpoint_foo_url = f"https://example.org/webhook/foo/{i}"
        endpoint_bar_url = f"https://example.org/webhook/bar/{i}"
        swh_webhooks.endpoint_create(
            Endpoint(
                url=endpoint_foo_url, event_type_name=event_type_name, channel="foo"
            )
        )
        swh_webhooks.endpoint_create(
            Endpoint(
                url=endpoint_bar_url, event_type_name=event_type_name, channel="bar"
            )
        )
        endpoint_foo_channel_urls.append(endpoint_foo_url)
        endpoint_bar_channel_urls.append(endpoint_bar_url)

    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "endpoint",
            "list",
            event_type_name,
            "--channel",
            "foo",
        ],
    )
    assert result.exit_code == 0

    assert "\n".join(list(reversed(endpoint_foo_channel_urls))) == result.output[:-1]

    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "endpoint",
            "list",
            event_type_name,
            "--channel",
            "bar",
        ],
    )
    assert result.exit_code == 0

    assert "\n".join(list(reversed(endpoint_bar_channel_urls))) == result.output[:-1]


def test_cli_delete_endpoint_auth_error(cli_runner, invalid_svix_credentials_options):
    result = cli_runner.invoke(
        cli,
        invalid_svix_credentials_options
        + [
            "endpoint",
            "delete",
            "origin.create",
            "https://example.org/webhook",
        ],
    )
    assert result.exit_code != 0

    assert (
        "Error: Svix server returned error 'authentication_failed' with detail 'Invalid token'"
        in result.output
    )


def test_cli_delete_endpoint_unkown_event_type(
    cli_runner, valid_svix_credentials_options
):
    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "endpoint",
            "delete",
            "origin.create",
            "https://example.org/webhook",
        ],
    )
    assert result.exit_code != 0

    assert "Error: Event type origin.create does not exist" in result.output


@pytest.mark.parametrize("with_channel", [False, True])
def test_cli_delete_endpoint_unkown_endpoint(
    cli_runner, valid_svix_credentials_options, swh_webhooks, with_channel
):
    endpoint_url = "https://example.org/webhook"
    channel = "foo"
    event_type_name = "origin.create"
    event_type = EventType(
        name=event_type_name,
        description="origin creation",
        schema={"type": "object"},
    )
    swh_webhooks.event_type_create(event_type)

    cmd = [
        "endpoint",
        "delete",
        event_type_name,
        endpoint_url,
    ]
    error_message = f"Error: Endpoint with url {endpoint_url} "
    if with_channel:
        cmd += [
            "--channel",
            channel,
        ]
        error_message += f"and channel {channel} "
    error_message += f"for event type {event_type_name} does not exist"

    result = cli_runner.invoke(cli, valid_svix_credentials_options + cmd)
    assert result.exit_code != 0

    assert error_message in result.output


def test_cli_delete_endpoint(cli_runner, valid_svix_credentials_options, swh_webhooks):
    endpoint_url = "https://example.org/webhook"
    event_type_name = "origin.create"
    event_type = EventType(
        name=event_type_name,
        description="origin creation",
        schema={"type": "object"},
    )
    swh_webhooks.event_type_create(event_type)

    endpoint = Endpoint(url=endpoint_url, event_type_name=event_type_name)
    swh_webhooks.endpoint_create(endpoint)

    assert list(swh_webhooks.endpoints_list(event_type_name=event_type_name)) == [
        endpoint
    ]

    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "endpoint",
            "delete",
            event_type_name,
            endpoint_url,
        ],
    )
    assert result.exit_code == 0

    assert list(swh_webhooks.endpoints_list(event_type_name=event_type_name)) == []


def test_cli_send_event_auth_error(cli_runner, invalid_svix_credentials_options):
    result = cli_runner.invoke(
        cli,
        invalid_svix_credentials_options
        + [
            "event",
            "send",
            "origin.create",
            "-",
        ],
        input="{}",
    )
    assert result.exit_code != 0

    assert (
        "Error: Svix server returned error 'authentication_failed' with detail 'Invalid token'"
        in result.output
    )


def test_cli_send_event_unknown_event_type(cli_runner, valid_svix_credentials_options):
    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "event",
            "send",
            "origin.create",
            "-",
        ],
        input="{}",
    )
    assert result.exit_code != 0

    assert "Error: Event type origin.create does not exist" in result.output


def test_cli_send_event_missing_payload_file(
    cli_runner, valid_svix_credentials_options, swh_webhooks
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
            "event",
            "send",
            event_type.name,
            "payload.json",
        ],
    )
    assert result.exit_code != 0

    assert (
        "Error: Invalid value for 'PAYLOAD_FILE': 'payload.json': No such file or directory"
        in result.output
    )


def test_cli_send_event_invalid_schema_for_payload(
    cli_runner, valid_svix_credentials_options, swh_webhooks, datadir
):
    event_type = EventType(
        name="origin.create",
        description="origin creation",
        schema=json.loads(Path(datadir, "origin_create.json").read_text()),
    )
    swh_webhooks.event_type_create(event_type)

    payload = {"foo": "bar"}

    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "event",
            "send",
            event_type.name,
            "-",
        ],
        input=json.dumps(payload),
    )

    assert result.exit_code != 0

    assert "Error: Payload validation against JSON schema failed" in result.output
    assert "'origin_url' is a required property" in result.output


def test_cli_send_event(
    cli_runner,
    valid_svix_credentials_options,
    swh_webhooks,
    datadir,
    tmp_path,
    httpserver,
):
    event_type = EventType(
        name="origin.create",
        description="origin creation",
        schema=json.loads(Path(datadir, "origin_create.json").read_text()),
    )
    swh_webhooks.event_type_create(event_type)

    endpoint_path = "/swh_webhook"
    endpoint = Endpoint(
        event_type_name=event_type.name,
        url=httpserver.url_for(endpoint_path),
    )
    swh_webhooks.endpoint_create(endpoint)

    payload = {"origin_url": "https://git.example.org/user/project"}
    payload_file_path = os.path.join(tmp_path, "payload.json")
    with open(payload_file_path, "w") as json_file:
        json.dump(payload, json_file)

    httpserver.expect_oneshot_request(
        endpoint_path,
        method="POST",
        json=payload,
    ).respond_with_data("OK")

    with httpserver.wait() as waiting:
        result = cli_runner.invoke(
            cli,
            valid_svix_credentials_options
            + [
                "event",
                "send",
                event_type.name,
                payload_file_path,
            ],
        )

    assert waiting.result
    httpserver.check()

    assert result.exit_code == 0
