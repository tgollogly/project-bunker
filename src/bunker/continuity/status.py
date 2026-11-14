from __future__ import annotations

import time
from typing import Any

from bunker.continuity.meta import read_sync_meta
from bunker.continuity.paths import ContinuityPaths


def continuity_status(paths: ContinuityPaths) -> list[dict[str, Any]]:
    paths.ensure()
    rows: list[dict[str, Any]] = []
    if not paths.meta_root.is_dir():
        return rows
    now = time.time()
    for meta_file in sorted(paths.meta_root.glob("*.json")):
        if meta_file.name == "watch_state.json" or meta_file.name.endswith(".delta.json"):
            continue
        source_id = meta_file.stem
        doc = read_sync_meta(paths.meta_root, source_id, continuity_root=paths.continuity_root)
        if not doc:
            continue
        age = now - float(doc.get("last_success_at", now))
        rows.append(
            {
                "source_id": source_id,
                "last_success_iso": doc.get("last_success_iso"),
                "age_seconds": int(age),
                "stale": age > 86400,
                "details": {k: v for k, v in doc.items() if k not in ("source_id",)},
            }
        )
    return rows