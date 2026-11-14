from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, cast

from bunker.continuity.encryption import decrypt_optional, encrypt_optional
from bunker.io.atomic import atomic_write_bytes


def write_sync_meta(meta_root: Path, source_id: str, extra: dict[str, Any] | None = None) -> None:
    meta_root.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {
        "source_id": source_id,
        "last_success_at": time.time(),
        "last_success_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if extra:
        doc.update(extra)
    path = meta_root / f"{source_id}.json"
    atomic_write_bytes(path, encrypt_optional(json.dumps(doc, indent=2).encode()))


def read_sync_meta(meta_root: Path, source_id: str) -> dict[str, Any] | None:
    path = meta_root / f"{source_id}.json"
    if not path.is_file():
        return None
    raw = decrypt_optional(path.read_bytes())
    return cast(dict[str, Any], json.loads(raw.decode()))