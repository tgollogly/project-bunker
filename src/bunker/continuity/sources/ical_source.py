from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from icalendar import Calendar

from bunker.continuity.meta import write_sync_meta
from bunker.continuity.parquet_io import replace_encrypted_partition_rows
from bunker.continuity.paths import ContinuityPaths

logger = logging.getLogger(__name__)


def _parse_ics_bytes(data: bytes) -> list[dict[str, Any]]:
    cal = Calendar.from_ical(data)
    rows: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        uid = str(component.get("UID", ""))
        summary = str(component.get("SUMMARY", ""))
        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")
        start_s = dtstart.dt.isoformat() if hasattr(dtstart, "dt") else str(dtstart)
        end_s = dtend.dt.isoformat() if hasattr(dtend, "dt") else str(dtend)
        location = str(component.get("LOCATION", "") or "")
        rows.append(
            {
                "id": uid or f"ical-{summary}-{start_s}",
                "subject": summary,
                "start": start_s,
                "end": end_s,
                "organizer": "",
                "location": location,
                "_bunker_ingested_at": now,
            }
        )
    return rows


def _load_ical(path_or_url: str, *, http: httpx.Client | None = None) -> bytes:
    parsed = urlparse(path_or_url)
    if parsed.scheme in ("http", "https"):
        if http is not None:
            resp = http.get(path_or_url, follow_redirects=True)
        else:
            with httpx.Client(timeout=60.0) as client:
                resp = client.get(path_or_url, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    p = Path(path_or_url).expanduser()
    if not p.is_file():
        raise FileNotFoundError(path_or_url)
    return p.read_bytes()


class IcalSource:
    def __init__(self, entry: dict[str, Any]) -> None:
        self.id = str(entry.get("id", "ical"))
        self._entry = entry

    def sync(self, paths: ContinuityPaths, cfg: dict[str, Any]) -> dict[str, Any]:
        urls = list(self._entry.get("urls") or [])
        files = list(self._entry.get("files") or [])
        feeds = urls + files
        if not feeds:
            logger.info("iCal source %s has no urls/files — skipping", self.id)
            return {"source_id": self.id, "type": "ical", "row_count": 0}
        rows: list[dict[str, Any]] = []
        with httpx.Client(timeout=60.0) as http:
            for feed in feeds:
                try:
                    rows.extend(_parse_ics_bytes(_load_ical(str(feed), http=http)))
                except Exception as exc:
                    logger.error("iCal feed %s failed: %s", feed, exc)
        partition = paths.parquet_root / "ical" / self.id / "calendar"
        replace_encrypted_partition_rows(partition, rows, continuity_root=paths.continuity_root)
        write_sync_meta(
            paths.meta_root,
            f"ical_{self.id}",
            {"row_count": len(rows)},
            continuity_root=paths.continuity_root,
        )
        return {"source_id": self.id, "type": "ical", "row_count": len(rows)}