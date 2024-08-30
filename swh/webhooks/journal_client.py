# Copyright (C) 2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from functools import partial
from typing import Any, Dict, List

import sentry_sdk

from swh.core.sentry import init_sentry
from swh.journal.client import JournalClient
from swh.model.swhids import CoreSWHID, ObjectType
from swh.webhooks.interface import Webhooks


def process_journal_objects(
    messages: Dict[str, List[Dict[str, Any]]], webhooks: Webhooks
):
    process_origins(messages.get("origin", []), webhooks)
    process_origin_visit_statuses(messages.get("origin_visit_status", []), webhooks)


def process_origins(origins: List[Dict[str, Any]], webhooks: Webhooks):
    for origin in origins:
        try:
            webhooks.event_send(
                "origin.create", {"origin_url": origin["url"]}, channel=origin["url"]
            )
        except Exception as e:
            sentry_sdk.capture_exception(e)


def process_origin_visit_statuses(
    origin_visit_statuses: List[Dict[str, Any]], webhooks: Webhooks
):
    for origin_visit_status in origin_visit_statuses:
        try:
            webhooks.event_send(
                "origin.visit",
                {
                    "origin_url": origin_visit_status["origin"],
                    "visit_type": origin_visit_status["type"],
                    "visit_date": origin_visit_status["date"].isoformat(),
                    "visit_status": origin_visit_status["status"],
                    "snapshot_swhid": (
                        str(
                            CoreSWHID(
                                object_type=ObjectType.SNAPSHOT,
                                object_id=origin_visit_status["snapshot"],
                            )
                        )
                        if origin_visit_status["snapshot"]
                        else None
                    ),
                },
                channel=origin_visit_status["origin"],
            )
        except Exception as e:
            sentry_sdk.capture_exception(e)


def process(client: JournalClient, webhooks: Webhooks):
    init_sentry()
    return client.process(partial(process_journal_objects, webhooks=webhooks))
