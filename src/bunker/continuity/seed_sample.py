"""Write clearly fake continuity sample data into the configured data root."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from typing import Any

from bunker.continuity.encryption import encrypt_at_rest
from bunker.continuity.meta import write_sync_meta
from bunker.continuity.parquet_io import clear_encrypted_partition, replace_encrypted_partition_rows
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.storage import write_encrypted_file
from bunker.io.atomic import atomic_write_bytes

logger = logging.getLogger(__name__)

SAMPLE_CONTACT_NAME = "Sam Sampleton"
SAMPLE_CONTACT_EMAIL = "sam.sampleton@example.invalid"
SAMPLE_RUNBOOK_FOLDER = "runbooks"
RUNBOOK_TITLE = "Outage checklist"
RUNBOOK_DESCRIPTION = "Offline steps when Microsoft 365 is unreachable (sample)."


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def seed_sample_data(paths: ContinuityPaths) -> dict[str, Any]:
    """
    Populate calendar, contacts, and a runbook document with fictional demo data.
    Uses encryption when BUNKER_DATA_KEY is set (required if continuity.require_encryption).
    """
    paths.ensure()
    clear_encrypted_partition(paths.parquet_root / "m365" / "calendar")
    clear_encrypted_partition(paths.parquet_root / "m365" / "contacts")
    runbook_dir = paths.docs_root / SAMPLE_RUNBOOK_FOLDER
    if runbook_dir.is_dir():
        shutil.rmtree(runbook_dir)
    now = datetime.now(timezone.utc)

    calendar_rows = [
        {
            "id": "sample-event-standup",
            "subject": "[SAMPLE] Team stand-up",
            "start": _iso(now.replace(hour=9, minute=0, second=0)),
            "end": _iso(now.replace(hour=9, minute=30, second=0)),
            "organizer": "Demo Organizer",
            "location": "Conference Room B (fictional)",
            "_bunker_ingested_at": now.isoformat(),
        },
        {
            "id": "sample-event-drill",
            "subject": "[SAMPLE] DR tabletop exercise",
            "start": _iso((now + timedelta(days=1)).replace(hour=14, minute=0, second=0)),
            "end": _iso((now + timedelta(days=1)).replace(hour=16, minute=0, second=0)),
            "organizer": "Demo Organizer",
            "location": "Virtual (offline cache only)",
            "_bunker_ingested_at": now.isoformat(),
        },
    ]
    replace_encrypted_partition_rows(
        paths.parquet_root / "m365" / "calendar",
        calendar_rows,
        continuity_root=paths.continuity_root,
    )
    write_sync_meta(
        paths.meta_root,
        "m365_calendar",
        {"row_count": len(calendar_rows), "sample": True, "horizon_days": 7},
        continuity_root=paths.continuity_root,
    )

    contact_rows = [
        {
            "id": "sample-contact-sam",
            "display_name": SAMPLE_CONTACT_NAME,
            "email": SAMPLE_CONTACT_EMAIL,
            "mobile": "+44 7700 900123",
            "company": "Example Corp (sample)",
            "_bunker_ingested_at": now.isoformat(),
        },
        {
            "id": "sample-contact-alex",
            "display_name": "Alex Example",
            "email": "alex.example@example.invalid",
            "mobile": "",
            "company": "Example Corp (sample)",
            "_bunker_ingested_at": now.isoformat(),
        },
    ]
    replace_encrypted_partition_rows(
        paths.parquet_root / "m365" / "contacts",
        contact_rows,
        continuity_root=paths.continuity_root,
    )
    write_sync_meta(
        paths.meta_root,
        "m365_contacts",
        {"row_count": len(contact_rows), "sample": True},
        continuity_root=paths.continuity_root,
    )

    runbook_plain = (
        "# SAMPLE runbook — not real procedures\n\n"
        "1. Confirm M365 status page.\n"
        "2. Open `bunker serve` on loopback.\n"
        "3. Use cached contacts and calendar.\n"
    ).encode()
    doc_dir = paths.docs_root / SAMPLE_RUNBOOK_FOLDER
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_path = doc_dir / "outage-checklist.md"
    enc_path = write_encrypted_file(
        doc_path, runbook_plain, continuity_root=paths.continuity_root
    )
    manifest = {
        "folder_id": SAMPLE_RUNBOOK_FOLDER,
        "synced_at": now.isoformat(),
        "sample": True,
        "files": [
            {
                "path": str(enc_path.relative_to(paths.continuity_root)),
                "name": "outage-checklist.md",
                "title": RUNBOOK_TITLE,
                "description": RUNBOOK_DESCRIPTION,
                "sha256": "sample-not-a-real-hash",
                "bytes": len(runbook_plain),
            }
        ],
    }
    manifest_path = paths.manifest_root / f"{SAMPLE_RUNBOOK_FOLDER}.json"
    atomic_write_bytes(
        manifest_path,
        encrypt_at_rest(
            json.dumps(manifest, indent=2).encode(),
            continuity_root=paths.continuity_root,
        ),
    )
    write_sync_meta(
        paths.meta_root,
        f"m365_docs_{SAMPLE_RUNBOOK_FOLDER}",
        {"file_count": 1, "sample": True},
        continuity_root=paths.continuity_root,
    )

    logger.info("Seeded sample continuity data under %s", paths.continuity_root)
    return {
        "calendar_events": len(calendar_rows),
        "contacts": len(contact_rows),
        "runbook_files": 1,
        "contact_name": SAMPLE_CONTACT_NAME,
        "data_root": str(paths.continuity_root),
    }