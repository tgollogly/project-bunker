from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from bunker.continuity.graph.client import HttpxGraphClient
from bunker.continuity.meta import write_sync_meta
from bunker.continuity.parquet_io import write_encrypted_parquet_rows
from bunker.continuity.paths import ContinuityPaths
from bunker.ingest.parquet_writer import hive_part_path

logger = logging.getLogger(__name__)


def _contact_rows(contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for c in contacts:
        emails = c.get("emailAddresses") or []
        primary = emails[0].get("address") if emails else None
        rows.append(
            {
                "id": c.get("id"),
                "display_name": c.get("displayName"),
                "email": primary,
                "mobile": (c.get("mobilePhone") or ""),
                "company": (c.get("companyName") or ""),
                "_bunker_ingested_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return rows


def sync_contacts(
    paths: ContinuityPaths,
    client: HttpxGraphClient,
    *,
    user: str = "me",
) -> dict[str, Any]:
    paths.ensure()
    page = client.get(f"/users/{user}/contacts?$top=200")
    contacts: list[dict[str, Any]] = list(page.get("value") or [])
    next_link = page.get("@odata.nextLink")
    while next_link:
        page = client.get(next_link)
        contacts.extend(page.get("value") or [])
        next_link = page.get("@odata.nextLink")

    rows = _contact_rows(contacts)
    partition = paths.parquet_root / "m365" / "contacts"
    if rows:
        part = hive_part_path(partition)
        write_encrypted_parquet_rows(rows, part, continuity_root=paths.continuity_root)

    write_sync_meta(
        paths.meta_root,
        "m365_contacts",
        {"row_count": len(rows)},
        continuity_root=paths.continuity_root,
    )
    logger.info("Contacts sync: %s rows", len(rows))
    return {"source": "m365_contacts", "contacts": len(rows)}