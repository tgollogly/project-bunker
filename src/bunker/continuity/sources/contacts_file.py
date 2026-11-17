from __future__ import annotations

import csv
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bunker.continuity.meta import write_sync_meta
from bunker.continuity.parquet_io import replace_encrypted_partition_rows
from bunker.continuity.paths import ContinuityPaths

logger = logging.getLogger(__name__)

_VCARD_FN = re.compile(r"^FN:(.+)$", re.MULTILINE | re.IGNORECASE)
_VCARD_EMAIL = re.compile(r"^EMAIL[^:]*:(.+)$", re.MULTILINE | re.IGNORECASE)
_VCARD_TEL = re.compile(r"^TEL[^:]*:(.+)$", re.MULTILINE | re.IGNORECASE)


def _rows_from_csv(path: Path) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            name = (row.get("name") or row.get("display_name") or row.get("Name") or "").strip()
            email = (row.get("email") or row.get("Email") or "").strip()
            mobile = (row.get("mobile") or row.get("phone") or row.get("Phone") or "").strip()
            company = (row.get("company") or row.get("Company") or "").strip()
            rows.append(
                {
                    "id": f"csv-{path.name}-{i}",
                    "display_name": name,
                    "email": email,
                    "mobile": mobile,
                    "company": company,
                    "_bunker_ingested_at": now,
                }
            )
    return rows


def _rows_from_vcard(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    cards = text.split("BEGIN:VCARD")
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for i, chunk in enumerate(cards):
        if "END:VCARD" not in chunk:
            continue
        fn = _VCARD_FN.search(chunk)
        email = _VCARD_EMAIL.search(chunk)
        tel = _VCARD_TEL.search(chunk)
        name = (fn.group(1).strip() if fn else f"contact-{i}")
        rows.append(
            {
                "id": f"vcard-{path.name}-{i}",
                "display_name": name,
                "email": email.group(1).strip() if email else "",
                "mobile": tel.group(1).strip() if tel else "",
                "company": "",
                "_bunker_ingested_at": now,
            }
        )
    return rows


class ContactsFileSource:
    def __init__(self, entry: dict[str, Any]) -> None:
        self.id = str(entry.get("id", "contacts_file"))
        self._entry = entry

    def sync(self, paths: ContinuityPaths, cfg: dict[str, Any]) -> dict[str, Any]:
        paths_list = [Path(p).expanduser() for p in (self._entry.get("paths") or [])]
        if not paths_list:
            return {"source_id": self.id, "type": "contacts_file", "row_count": 0}
        rows: list[dict[str, Any]] = []
        for p in paths_list:
            if not p.is_file():
                logger.warning("Contacts file missing: %s", p)
                continue
            suffix = p.suffix.lower()
            if suffix == ".csv":
                rows.extend(_rows_from_csv(p))
            elif suffix in (".vcf", ".vcard"):
                rows.extend(_rows_from_vcard(p))
            else:
                logger.warning("Unsupported contacts file type: %s", p)
        partition = paths.parquet_root / "files" / self.id / "contacts"
        replace_encrypted_partition_rows(partition, rows, continuity_root=paths.continuity_root)
        write_sync_meta(
            paths.meta_root,
            f"contacts_{self.id}",
            {"row_count": len(rows)},
            continuity_root=paths.continuity_root,
        )
        return {"source_id": self.id, "type": "contacts_file", "row_count": len(rows)}