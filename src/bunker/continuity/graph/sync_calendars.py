from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from bunker.continuity.encryption import encrypt_at_rest
from bunker.continuity.graph.client import HttpxGraphClient
from bunker.continuity.meta import write_sync_meta
from bunker.continuity.parquet_io import write_encrypted_parquet_rows
from bunker.continuity.paths import ContinuityPaths
from bunker.ingest.parquet_writer import hive_part_path
from bunker.io.atomic import atomic_write_bytes

logger = logging.getLogger(__name__)


def _event_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ev in events:
        rows.append(
            {
                "id": ev.get("id"),
                "subject": ev.get("subject"),
                "start": (ev.get("start") or {}).get("dateTime"),
                "end": (ev.get("end") or {}).get("dateTime"),
                "organizer": ((ev.get("organizer") or {}).get("emailAddress") or {}).get("name"),
                "location": (ev.get("location") or {}).get("displayName"),
                "_bunker_ingested_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return rows


def sync_calendars(
    paths: ContinuityPaths,
    client: HttpxGraphClient,
    *,
    user: str = "me",
    horizon_days: int = 14,
) -> dict[str, Any]:
    paths.ensure()
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=horizon_days)
    delta_path = paths.meta_root / "calendar.delta.json"
    delta_link: str | None = None
    if delta_path.is_file():
        from bunker.continuity.encryption import decrypt_at_rest

        delta_link = json.loads(
            decrypt_at_rest(delta_path.read_bytes(), continuity_root=paths.continuity_root).decode()
        ).get("deltaLink")

    if delta_link:
        page = client.get(delta_link)
    else:
        qs = (
            f"?startDateTime={start.isoformat()}&endDateTime={end.isoformat()}"
            "&$top=200"
        )
        page = client.get(f"/users/{user}/calendarView{qs}")

    events: list[dict[str, Any]] = list(page.get("value") or [])
    next_link = page.get("@odata.nextLink")
    while next_link:
        page = client.get(next_link)
        events.extend(page.get("value") or [])
        next_link = page.get("@odata.nextLink")

    if page.get("@odata.deltaLink"):
        atomic_write_bytes(
            delta_path,
            encrypt_at_rest(
                json.dumps({"deltaLink": page["@odata.deltaLink"]}, indent=2).encode(),
                continuity_root=paths.continuity_root,
            ),
        )

    rows = _event_rows(events)
    partition = paths.parquet_root / "m365" / "calendar"
    if rows:
        part = hive_part_path(partition)
        write_encrypted_parquet_rows(rows, part, continuity_root=paths.continuity_root)

    write_sync_meta(
        paths.meta_root,
        "m365_calendar",
        {"row_count": len(rows), "horizon_days": horizon_days},
        continuity_root=paths.continuity_root,
    )
    logger.info("Calendar sync: %s events", len(rows))
    return {"source": "m365_calendar", "events": len(rows)}