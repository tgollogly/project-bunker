from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from bunker.continuity.google.auth import GoogleTokenProvider
from bunker.continuity.meta import write_sync_meta
from bunker.continuity.parquet_io import replace_encrypted_partition_rows
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.sources.local_folder import sync_local_folder

logger = logging.getLogger(__name__)

_CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
_PEOPLE_BASE = "https://people.googleapis.com/v1"


def _event_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for ev in events:
        start = ev.get("start") or {}
        end = ev.get("end") or {}
        rows.append(
            {
                "id": ev.get("id"),
                "subject": ev.get("summary"),
                "start": start.get("dateTime") or start.get("date"),
                "end": end.get("dateTime") or end.get("date"),
                "organizer": (ev.get("organizer") or {}).get("email"),
                "location": ev.get("location"),
                "_bunker_ingested_at": now,
            }
        )
    return rows


def _contact_rows(people: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for person in people:
        names = person.get("names") or []
        display = names[0].get("displayName") if names else ""
        emails = person.get("emailAddresses") or []
        email = emails[0].get("value") if emails else ""
        phones = person.get("phoneNumbers") or []
        mobile = phones[0].get("value") if phones else ""
        rows.append(
            {
                "id": person.get("resourceName"),
                "display_name": display,
                "email": email,
                "mobile": mobile,
                "company": "",
                "_bunker_ingested_at": now,
            }
        )
    return rows


class GoogleWorkspaceSource:
    def __init__(self, entry: dict[str, Any]) -> None:
        self.id = str(entry.get("id", "google"))
        self._entry = entry

    def sync(self, paths: ContinuityPaths, cfg: dict[str, Any]) -> dict[str, Any]:
        cont = cfg.get("continuity", {})
        horizon = int(cont.get("calendar_horizon_days", 14))
        calendar_id = str(self._entry.get("calendar_id", "primary"))
        token_provider = GoogleTokenProvider.from_env()
        token = token_provider.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        time_min = datetime.now(timezone.utc)
        time_max = time_min + timedelta(days=horizon)

        with httpx.Client(timeout=60.0) as http:
            cal_resp = http.get(
                f"{_CALENDAR_BASE}/calendars/{calendar_id}/events",
                params={
                    "timeMin": time_min.isoformat().replace("+00:00", "Z"),
                    "timeMax": time_max.isoformat().replace("+00:00", "Z"),
                    "singleEvents": "true",
                    "orderBy": "startTime",
                    "maxResults": 250,
                },
                headers=headers,
            )
            cal_resp.raise_for_status()
            events = cal_resp.json().get("items") or []

            people_resp = http.get(
                f"{_PEOPLE_BASE}/people/me/connections",
                params={"personFields": "names,emailAddresses,phoneNumbers", "pageSize": 250},
                headers=headers,
            )
            people_resp.raise_for_status()
            people = people_resp.json().get("connections") or []

        cal_rows = _event_rows(events)
        replace_encrypted_partition_rows(
            paths.parquet_root / "google" / "calendar",
            cal_rows,
            continuity_root=paths.continuity_root,
        )
        write_sync_meta(
            paths.meta_root,
            "google_calendar",
            {"row_count": len(cal_rows), "horizon_days": horizon},
            continuity_root=paths.continuity_root,
        )

        contact_rows = _contact_rows(people)
        replace_encrypted_partition_rows(
            paths.parquet_root / "google" / "contacts",
            contact_rows,
            continuity_root=paths.continuity_root,
        )
        write_sync_meta(
            paths.meta_root,
            "google_contacts",
            {"row_count": len(contact_rows)},
            continuity_root=paths.continuity_root,
        )

        drive_folder = (self._entry.get("drive_folder") or "").strip()
        doc_result: dict[str, Any] | None = None
        if drive_folder:
            doc_result = sync_local_folder(
                paths,
                folder_id=str(self._entry.get("docs_id", "google_drive")),
                local_path=drive_folder,
            )

        return {
            "source_id": self.id,
            "type": "google_workspace",
            "calendar_rows": len(cal_rows),
            "contact_rows": len(contact_rows),
            "documents": doc_result,
        }