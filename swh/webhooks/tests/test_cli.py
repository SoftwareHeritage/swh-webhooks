# Copyright (C) 2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information


from collections import defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import textwrap
import time

import pytest

from swh.webhooks.cli import webhooks_cli_group as cli
from swh.webhooks.interface import Endpoint, EventType


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


@pytest.fixture
def origin_create_event_type(datadir, swh_webhooks):
    event_type = EventType(
        name="origin.create",
        description="origin creation",
        schema=json.loads(Path(datadir, "origin_create.json").read_text()),
    )
    swh_webhooks.event_type_create(event_type)
    return event_type


@pytest.fixture
def origin_visit_event_type(datadir, swh_webhooks):
    event_type = EventType(
        name="origin.visit",
        description="origin visit",
        schema=json.loads(Path(datadir, "origin_visit.json").read_text()),
    )
    swh_webhooks.event_type_create(event_type)
    return event_type


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


def test_cli_register_default_event_types_auth_error(
    cli_runner, invalid_svix_credentials_options
):
    result = cli_runner.invoke(
        cli, invalid_svix_credentials_options + ["event-type", "register-defaults"]
    )

    assert result.exit_code != 0

    assert (
        "Error: Svix server returned error 'authentication_failed' with detail 'Invalid token'"
        in result.output
    )


def test_cli_register_default_event_types(
    cli_runner, valid_svix_credentials_options, swh_webhooks
):
    result = cli_runner.invoke(
        cli, valid_svix_credentials_options + ["event-type", "register-defaults"]
    )
    assert result.exit_code == 0

    assert swh_webhooks.event_types_list()


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
    origin_create_event_type,
):
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
    assert f"{origin_create_event_type.description}\n" in result.output
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
    assert result.output[0] == "{" and result.output[-2] == "}"


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
    cli_runner, valid_svix_credentials_options, origin_create_event_type, swh_webhooks
):
    assert swh_webhooks.event_type_get(origin_create_event_type.name)

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

    with pytest.raises(
        ValueError, match=f"Event type {origin_create_event_type.name} is archived"
    ):
        swh_webhooks.event_type_get(origin_create_event_type.name)


def test_cli_list_event_types_auth_error(cli_runner, invalid_svix_credentials_options):
    result = cli_runner.invoke(
        cli,
        invalid_svix_credentials_options
        + [
            "event-type",
            "list",
        ],
    )
    assert result.exit_code != 0

    assert (
        "Error: Svix server returned error 'authentication_failed' with detail 'Invalid token'"
        in result.output
    )


def test_cli_list_event_types_none(cli_runner, valid_svix_credentials_options):
    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "event-type",
            "list",
        ],
    )
    assert result.exit_code == 0

    assert "No event type registered" in result.output


def test_cli_list_event_types(
    cli_runner,
    valid_svix_credentials_options,
    origin_create_event_type,
    origin_visit_event_type,
):
    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "event-type",
            "list",
        ],
    )
    assert result.exit_code == 0

    for event_type in (origin_create_event_type, origin_visit_event_type):
        assert event_type.name in result.output
        assert event_type.description in result.output


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


@pytest.mark.parametrize(
    "with_channel,with_secret",
    [
        pytest.param(False, False, id="without channel and secret"),
        pytest.param(False, True, id="without channel and with secret"),
        pytest.param(True, False, id="with channel and without secret"),
        pytest.param(True, True, id="with channel and secret"),
    ],
)
def test_cli_create_endpoint(
    cli_runner,
    valid_svix_credentials_options,
    swh_webhooks,
    origin_create_event_type,
    with_channel,
    with_secret,
):
    url = "https://example.org/webhook"
    channel = "foo" if with_channel else None

    cmd = [
        "endpoint",
        "create",
        origin_create_event_type.name,
        url,
    ]
    if with_channel:
        cmd += [
            "--channel",
            channel,
        ]
    if with_secret:
        secret = "whsec_" + "b" * 32
        cmd += [
            "--secret",
            secret,
        ]

    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options + cmd,
    )
    assert result.exit_code == 0

    endpoints = list(
        swh_webhooks.endpoints_list(
            event_type_name=origin_create_event_type.name, channel=channel
        )
    )

    assert endpoints
    assert endpoints[0].event_type_name == origin_create_event_type.name
    assert endpoints[0].url == url
    assert endpoints[0].channel == channel

    # check same command call does not terminate with error
    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options + cmd,
    )
    assert result.exit_code == 0

    # check endpoint secret retrieval
    cmd = [
        "endpoint",
        "get-secret",
        origin_create_event_type.name,
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
    if with_secret:
        assert result.output[:-1] == secret
    else:
        assert result.output.startswith("whsec_")


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


@pytest.mark.parametrize("limit", [None, 5, 10, 15], ids=lambda li: f"limit={li}")
def test_cli_list_endpoints(
    cli_runner,
    valid_svix_credentials_options,
    swh_webhooks,
    origin_create_event_type,
    limit,
):
    endpoint_urls = []
    for i in range(10):
        endpoint_url = f"https://example.org/webhook/{i}"
        swh_webhooks.endpoint_create(
            Endpoint(url=endpoint_url, event_type_name=origin_create_event_type.name)
        )
        endpoint_urls.append(endpoint_url)

    cmd = [
        "endpoint",
        "list",
        origin_create_event_type.name,
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
    cli_runner, valid_svix_credentials_options, swh_webhooks, origin_create_event_type
):
    endpoint_foo_channel_urls = []
    endpoint_bar_channel_urls = []
    for i in range(10):
        endpoint_foo_url = f"https://example.org/webhook/foo/{i}"
        endpoint_bar_url = f"https://example.org/webhook/bar/{i}"
        swh_webhooks.endpoint_create(
            Endpoint(
                url=endpoint_foo_url,
                event_type_name=origin_create_event_type.name,
                channel="foo",
            )
        )
        swh_webhooks.endpoint_create(
            Endpoint(
                url=endpoint_bar_url,
                event_type_name=origin_create_event_type.name,
                channel="bar",
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
            origin_create_event_type.name,
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
            origin_create_event_type.name,
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


@pytest.mark.parametrize(
    "with_channel", [False, True], ids=["without channel", "with channel"]
)
def test_cli_delete_endpoint_unkown_endpoint(
    cli_runner,
    valid_svix_credentials_options,
    swh_webhooks,
    origin_create_event_type,
    with_channel,
):
    endpoint_url = "https://example.org/webhook"
    channel = "foo"

    cmd = [
        "endpoint",
        "delete",
        origin_create_event_type.name,
        endpoint_url,
    ]
    error_message = f"Error: Endpoint with url {endpoint_url} "
    if with_channel:
        cmd += [
            "--channel",
            channel,
        ]
        error_message += f"and channel {channel} "
    error_message += f"for event type {origin_create_event_type.name} does not exist"

    result = cli_runner.invoke(cli, valid_svix_credentials_options + cmd)
    assert result.exit_code != 0

    assert error_message in result.output


def test_cli_delete_endpoint(
    cli_runner, valid_svix_credentials_options, swh_webhooks, origin_create_event_type
):
    endpoint_url = "https://example.org/webhook"

    endpoint = Endpoint(url=endpoint_url, event_type_name=origin_create_event_type.name)
    swh_webhooks.endpoint_create(endpoint)

    assert list(
        swh_webhooks.endpoints_list(event_type_name=origin_create_event_type.name)
    ) == [endpoint]

    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "endpoint",
            "delete",
            origin_create_event_type.name,
            endpoint_url,
        ],
    )
    assert result.exit_code == 0

    assert (
        list(swh_webhooks.endpoints_list(event_type_name=origin_create_event_type.name))
        == []
    )


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
    cli_runner, valid_svix_credentials_options, swh_webhooks, origin_create_event_type
):
    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "event",
            "send",
            origin_create_event_type.name,
            "payload.json",
        ],
    )
    assert result.exit_code != 0

    assert (
        "Error: Invalid value for 'PAYLOAD_FILE': 'payload.json': No such file or directory"
        in result.output
    )


def test_cli_send_event_invalid_schema_for_payload(
    cli_runner, valid_svix_credentials_options, origin_create_event_type
):
    payload = {"foo": "bar"}

    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "event",
            "send",
            origin_create_event_type.name,
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
    origin_create_event_type,
    tmp_path,
    httpserver,
):
    endpoint_path = "/swh_webhook"
    endpoint = Endpoint(
        event_type_name=origin_create_event_type.name,
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
                origin_create_event_type.name,
                payload_file_path,
            ],
        )

    assert waiting.result
    httpserver.check()

    assert result.exit_code == 0


@pytest.mark.parametrize(
    "with_endpoint", [False, True], ids=["without endpoint", "with endpoint"]
)
def test_cli_list_events_auth_error(
    cli_runner, invalid_svix_credentials_options, with_endpoint
):
    cmd = [
        "event",
        "list",
        "origin.create",
    ]
    if with_endpoint:
        cmd += [
            "--endpoint-url",
            "https://example.org/wh",
        ]

    result = cli_runner.invoke(
        cli,
        invalid_svix_credentials_options + cmd,
    )

    assert result.exit_code != 0

    assert (
        "Error: Svix server returned error 'authentication_failed' with detail 'Invalid token'"
        in result.output
    )


@pytest.mark.parametrize(
    "with_endpoint", [False, True], ids=["without endpoint", "with endpoint"]
)
def test_cli_list_events_unknown_event_type(
    cli_runner, valid_svix_credentials_options, with_endpoint
):
    cmd = [
        "event",
        "list",
        "origin.create",
    ]
    if with_endpoint:
        cmd += [
            "--endpoint-url",
            "https://example.org/wh",
        ]
    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options + cmd,
    )
    assert result.exit_code != 0

    assert "Error: Event type origin.create does not exist" in result.output


@pytest.mark.parametrize("limit", [1, 5, 10], ids=lambda li: f"limit={li}")
def test_cli_list_events_for_event_type(
    cli_runner,
    valid_svix_credentials_options,
    swh_webhooks,
    httpserver,
    origin_create_event_type,
    limit,
):
    endpoint_path = "/swh_webhook"
    endpoint = Endpoint(
        event_type_name=origin_create_event_type.name,
        url=httpserver.url_for(endpoint_path),
    )
    swh_webhooks.endpoint_create(endpoint)

    payload = {"origin_url": "https://git.example.org/user/project"}

    nb_events = 10

    for _ in range(nb_events):
        httpserver.expect_oneshot_request(
            endpoint_path,
            method="POST",
            json=payload,
        ).respond_with_data("OK")

    with httpserver.wait() as waiting:
        for _ in range(nb_events):
            swh_webhooks.event_send(origin_create_event_type.name, payload)

    assert waiting.result
    httpserver.check()

    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "event",
            "list",
            "--limit",
            limit,
            origin_create_event_type.name,
        ],
    )

    assert result.exit_code == 0

    events = json.loads(result.output)

    assert len(events) == limit


def test_cli_list_events_for_event_type_with_channel(
    cli_runner,
    valid_svix_credentials_options,
    swh_webhooks,
    httpserver,
    origin_create_event_type,
):
    origin_url = "https://git.example.org/user/project1"
    other_origin_url = "https://git.example.org/user/project2"

    # first endpoint with channel set to origin_url
    first_endpoint_path = "/swh_webhook"
    first_endpoint_with_origin_channel = Endpoint(
        event_type_name=origin_create_event_type.name,
        url=httpserver.url_for(first_endpoint_path),
        channel=origin_url,
    )
    swh_webhooks.endpoint_create(first_endpoint_with_origin_channel)

    # second endpoint with no channel set
    second_endpoint_path = "/swh_webhook_other"
    second_endpoint_no_channel = Endpoint(
        event_type_name=origin_create_event_type.name,
        url=httpserver.url_for(second_endpoint_path),
    )
    swh_webhooks.endpoint_create(second_endpoint_no_channel)

    # third endpoint with channel set to other_origin_url
    third_endpoint_path = "/swh_webhook_another"
    third_endpoint_with_other_channel = Endpoint(
        event_type_name=origin_create_event_type.name,
        url=httpserver.url_for(third_endpoint_path),
        channel=other_origin_url,
    )
    swh_webhooks.endpoint_create(third_endpoint_with_other_channel)

    payload = {"origin_url": origin_url}

    # first endpoint should receive webhook events
    httpserver.expect_oneshot_request(
        first_endpoint_path,
        method="POST",
        json=payload,
    ).respond_with_data("OK")
    # second endpoint too
    httpserver.expect_oneshot_request(
        second_endpoint_path,
        method="POST",
        json=payload,
    ).respond_with_data("OK")

    with httpserver.wait() as waiting:
        # send webhook event on channel
        swh_webhooks.event_send(
            origin_create_event_type.name, payload, channel=origin_url
        )

    # check expected requests were received
    assert waiting.result
    # check no extra requests were sent
    httpserver.check()

    # list events for event type
    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "event",
            "list",
            "--channel",
            origin_url,
            "--limit",
            3,  # set limit to 3 to check third endpoint did not receive event
            origin_create_event_type.name,
        ],
    )

    assert result.exit_code == 0

    events = json.loads(result.output)

    # events sent to the two first endpoints should be listed
    assert len(events) == 2

    # check all expected events
    events_by_channel = defaultdict(list)
    for event in events:
        events_by_channel[event["channel"]].append(event)
    assert set(events_by_channel) == {origin_url, None}
    assert len(events_by_channel[origin_url]) == len(events_by_channel[None]) == 1
    assert all(
        event["endpoint_url"] == first_endpoint_with_origin_channel.url
        for event in events_by_channel[origin_url]
    )
    assert all(
        event["endpoint_url"] == second_endpoint_no_channel.url
        for event in events_by_channel[None]
    )


@pytest.mark.parametrize("limit", [1, 5, 10], ids=lambda li: f"limit={li}")
def test_cli_list_events_for_endpoint(
    cli_runner,
    valid_svix_credentials_options,
    swh_webhooks,
    httpserver,
    origin_create_event_type,
    limit,
):
    first_endpoint_path = "/swh_webhook"
    first_endpoint = Endpoint(
        event_type_name=origin_create_event_type.name,
        url=httpserver.url_for(first_endpoint_path),
    )
    swh_webhooks.endpoint_create(first_endpoint)

    second_endpoint_path = "/swh_webhook_other"
    second_endpoint = Endpoint(
        event_type_name=origin_create_event_type.name,
        url=httpserver.url_for(second_endpoint_path),
    )
    swh_webhooks.endpoint_create(second_endpoint)

    payload = {"origin_url": "https://git.example.org/user/project"}

    nb_events = 10

    for _ in range(nb_events):
        httpserver.expect_oneshot_request(
            first_endpoint_path,
            method="POST",
            json=payload,
        ).respond_with_data("OK")
        httpserver.expect_oneshot_request(
            second_endpoint_path,
            method="POST",
            json=payload,
        ).respond_with_data("OK")

    with httpserver.wait() as waiting:
        for _ in range(nb_events):
            swh_webhooks.event_send(origin_create_event_type.name, payload)

    assert waiting.result
    httpserver.check()

    for endpoint in (first_endpoint, second_endpoint):
        result = cli_runner.invoke(
            cli,
            valid_svix_credentials_options
            + [
                "event",
                "list",
                "--endpoint-url",
                endpoint.url,
                "--limit",
                limit,
                origin_create_event_type.name,
            ],
        )

        assert result.exit_code == 0

        events = json.loads(result.output)

        assert len(events) == limit
        assert all(event["endpoint_url"] == endpoint.url for event in events)


def test_cli_list_events_for_endpoint_with_channel(
    cli_runner,
    valid_svix_credentials_options,
    swh_webhooks,
    httpserver,
    origin_create_event_type,
):
    origin_url = "https://git.example.org/user/project1"
    other_origin_url = "https://git.example.org/user/project2"

    # first endpoint with channel set to origin_url
    first_endpoint_path = "/swh_webhook"
    first_endpoint_with_origin_channel = Endpoint(
        event_type_name=origin_create_event_type.name,
        url=httpserver.url_for(first_endpoint_path),
        channel=origin_url,
    )
    swh_webhooks.endpoint_create(first_endpoint_with_origin_channel)

    # second endpoint with no channel set
    second_endpoint_path = "/swh_webhook_other"
    second_endpoint_no_channel = Endpoint(
        event_type_name=origin_create_event_type.name,
        url=httpserver.url_for(second_endpoint_path),
    )
    swh_webhooks.endpoint_create(second_endpoint_no_channel)

    # third endpoint with channel set to other_origin_url
    third_endpoint_path = "/swh_webhook_another"
    third_endpoint_with_other_channel = Endpoint(
        event_type_name=origin_create_event_type.name,
        url=httpserver.url_for(third_endpoint_path),
        channel=other_origin_url,
    )
    swh_webhooks.endpoint_create(third_endpoint_with_other_channel)

    payload = {"origin_url": origin_url}

    # first endpoint should receive webhook events
    httpserver.expect_oneshot_request(
        first_endpoint_path,
        method="POST",
        json=payload,
    ).respond_with_data("OK")
    # second endpoint too
    httpserver.expect_oneshot_request(
        second_endpoint_path,
        method="POST",
        json=payload,
    ).respond_with_data("OK")

    with httpserver.wait() as waiting:
        # send webhook event on channel
        swh_webhooks.event_send(
            origin_create_event_type.name, payload, channel=origin_url
        )

    # check expected requests were received
    assert waiting.result
    # check no extra requests were sent
    httpserver.check()

    # check first and second endpoints received the expected events
    for endpoint in (first_endpoint_with_origin_channel, second_endpoint_no_channel):
        cmd = [
            "event",
            "list",
            origin_create_event_type.name,
            "--endpoint-url",
            endpoint.url,
        ]

        if endpoint.channel:
            cmd += [
                "--channel",
                endpoint.channel,
            ]

        result = cli_runner.invoke(
            cli,
            valid_svix_credentials_options + cmd,
        )

        assert result.exit_code == 0

        events = json.loads(result.output)

        assert len(events) == 1
        assert all(event["endpoint_url"] == endpoint.url for event in events)
        if endpoint.channel:
            assert all(event["channel"] == endpoint.channel for event in events)
        else:
            assert all(event["channel"] is None for event in events)

    # check third endpoint did not receive any events
    result = cli_runner.invoke(
        cli,
        valid_svix_credentials_options
        + [
            "event",
            "list",
            origin_create_event_type.name,
            "--endpoint-url",
            third_endpoint_with_other_channel.url,
            "--channel",
            third_endpoint_with_other_channel.channel,
        ],
    )

    assert result.exit_code == 0

    events = json.loads(result.output)

    assert len(events) == 0


@pytest.mark.parametrize(
    "for_endpoint", [False, True], ids=["for event type", "for endpoint"]
)
def test_cli_list_events_date_filtering(
    cli_runner,
    valid_svix_credentials_options,
    swh_webhooks,
    httpserver,
    origin_create_event_type,
    for_endpoint,
    mocker,
    mock_sleep,
):
    mocker.stop(mock_sleep)

    first_origin_url = "https://git.example.org/project1"
    second_origin_url = "https://git.example.org/project2"
    third_origin_url = "https://git.example.org/project3"

    first_origin_payload = {"origin_url": first_origin_url}
    second_origin_payload = {"origin_url": second_origin_url}
    third_origin_payload = {"origin_url": third_origin_url}

    endpoint_path = "/swh_webhook"
    endpoint = Endpoint(
        event_type_name=origin_create_event_type.name,
        url=httpserver.url_for(endpoint_path),
    )
    swh_webhooks.endpoint_create(endpoint)

    for payload in (first_origin_payload, second_origin_payload, third_origin_payload):
        httpserver.expect_oneshot_request(
            endpoint_path,
            method="POST",
            json=payload,
        ).respond_with_data("OK")

    with httpserver.wait() as waiting:
        # send webhook event on channel
        swh_webhooks.event_send(origin_create_event_type.name, first_origin_payload)
        time.sleep(1)
        after_first_sent_event = datetime.now(tz=timezone.utc)
        swh_webhooks.event_send(origin_create_event_type.name, second_origin_payload)
        time.sleep(1)
        after_second_sent_event = datetime.now(tz=timezone.utc)
        swh_webhooks.event_send(origin_create_event_type.name, third_origin_payload)

    assert waiting.result
    httpserver.check()

    base_cmd = [
        "event",
        "list",
        origin_create_event_type.name,
    ]

    if for_endpoint:
        base_cmd += [
            "--endpoint-url",
            endpoint.url,
        ]

    for date_options, expected_payloads in [
        (
            [
                "--before",
                after_first_sent_event.isoformat(),
            ],
            [first_origin_payload],
        ),
        (
            [
                "--after",
                after_second_sent_event.isoformat(),
            ],
            [third_origin_payload],
        ),
        (
            [
                "--before",
                after_second_sent_event.isoformat(),
            ],
            [second_origin_payload, first_origin_payload],
        ),
        (
            [
                "--after",
                after_first_sent_event.isoformat(),
            ],
            [third_origin_payload, second_origin_payload],
        ),
    ]:
        result = cli_runner.invoke(
            cli,
            valid_svix_credentials_options + base_cmd + date_options,
        )

        assert result.exit_code == 0
        events = json.loads(result.output)
        assert [event["payload"] for event in events] == expected_payloads
