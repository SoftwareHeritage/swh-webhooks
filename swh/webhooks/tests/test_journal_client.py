# Copyright (C) 2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from swh.journal.client import JournalClient
from swh.journal.writer import model_object_dict_sanitizer
from swh.journal.writer.kafka import KafkaJournalWriter
from swh.model.hashutil import hash_to_bytes
from swh.model.model import Origin, OriginVisitStatus
from swh.webhooks.cli import webhooks_cli_group as cli
from swh.webhooks.interface import Endpoint, EventType
from swh.webhooks.journal_client import process


@pytest.mark.parametrize("use_cli", [False, True], ids=["without CLI", "with CLI"])
def test_journal_client(
    kafka_prefix,
    kafka_consumer_group,
    kafka_server,
    swh_webhooks,
    httpserver,
    datadir,
    cli_runner,
    svix_server_url,
    svix_auth_token,
    use_cli,
):
    origin_create_endpoint_path = "/origin"
    origin_visit_endpoint_path = "/origin_visit"

    origin_create_event_type = EventType(
        name="origin.create",
        description="triggered after the creation of a new origin",
        schema=json.loads(Path(datadir, "origin_create.json").read_text()),
    )
    swh_webhooks.event_type_create(origin_create_event_type)

    origin_visit_event_type = EventType(
        name="origin.visit",
        description="triggered after the visit of an origin",
        schema=json.loads(Path(datadir, "origin_visit.json").read_text()),
    )
    swh_webhooks.event_type_create(origin_visit_event_type)

    origin_create_event_type = Endpoint(
        url=httpserver.url_for(origin_create_endpoint_path),
        event_type_name=origin_create_event_type.name,
    )
    swh_webhooks.endpoint_create(origin_create_event_type)

    origin_visit_endpoint = Endpoint(
        url=httpserver.url_for(origin_visit_endpoint_path),
        event_type_name=origin_visit_event_type.name,
    )
    swh_webhooks.endpoint_create(origin_visit_endpoint)

    writer = KafkaJournalWriter(
        brokers=[kafka_server],
        client_id="kafka_writer",
        prefix=kafka_prefix,
        value_sanitizer=model_object_dict_sanitizer,
        anonymize=False,
    )

    origin_url = "https://git.example.org/project"
    origin = Origin(url=origin_url)
    some_sha1 = "1" * 40
    origin_visit_status = OriginVisitStatus(
        origin=origin_url,
        visit=1,
        date=datetime.now(tz=timezone.utc),
        status="full",
        snapshot=hash_to_bytes(some_sha1),
        type="git",
    )

    writer.write_addition("origin", origin)
    writer.write_addition("origin_visit_status", origin_visit_status)

    expected_origin_create_payload = {"origin_url": origin_url}
    expected_origin_visit_payload = {
        "origin_url": origin_visit_status.origin,
        "visit_type": origin_visit_status.type,
        "visit_date": origin_visit_status.date.isoformat(),
        "visit_status": origin_visit_status.status,
        "snapshot_swhid": f"swh:1:snp:{some_sha1}",
    }

    httpserver.expect_oneshot_request(
        origin_create_endpoint_path,
        method="POST",
        json=expected_origin_create_payload,
    ).respond_with_data("OK")

    httpserver.expect_oneshot_request(
        origin_visit_endpoint_path,
        method="POST",
        json=expected_origin_visit_payload,
    ).respond_with_data("OK")

    with httpserver.wait() as waiting:
        if use_cli:
            result = cli_runner.invoke(
                cli,
                [
                    "--svix-url",
                    svix_server_url,
                    "--svix-token",
                    svix_auth_token,
                    "journal-client",
                    "--broker",
                    kafka_server,
                    "--prefix",
                    kafka_prefix,
                    "--group-id",
                    kafka_consumer_group,
                    "--stop-after-objects",
                    2,
                ],
            )
            assert result.exit_code == 0
        else:
            client = JournalClient(
                brokers=[kafka_server],
                group_id=kafka_consumer_group,
                prefix=kafka_prefix,
                object_types=["origin", "origin_visit_status"],
                create_topics=True,
                stop_after_objects=2,
            )
            process(client, swh_webhooks)

    assert waiting.result
    httpserver.check()
