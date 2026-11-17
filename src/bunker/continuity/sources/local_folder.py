from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bunker.continuity.encryption import encrypt_at_rest
from bunker.continuity.meta import write_sync_meta
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.storage import write_encrypted_file
from bunker.io.atomic import atomic_write_bytes

logger = logging.getLogger(__name__)

_ALLOWED_SUFFIXES = {".md", ".txt", ".pdf", ".docx", ".html", ".json"}


def sync_local_folder(
    paths: ContinuityPaths,
    *,
    folder_id: str,
    local_path: str,
) -> dict[str, Any]:
    """Copy allowed files from a local directory into encrypted docs storage."""
    src = Path(local_path).expanduser().resolve()
    if not src.is_dir():
        raise NotADirectoryError(local_path)
    dest_root = paths.docs_root / folder_id
    if dest_root.is_dir():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix.lower() not in _ALLOWED_SUFFIXES:
            continue
        rel = f.relative_to(src)
        if ".." in rel.parts:
            continue
        target = dest_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = f.read_bytes()
        if f.suffix.lower() in {".md", ".txt", ".html", ".json"}:
            write_encrypted_file(target, raw, continuity_root=paths.continuity_root)
        else:
            enc = target.with_suffix(target.suffix + ".enc")
            atomic_write_bytes(
                enc,
                encrypt_at_rest(raw, continuity_root=paths.continuity_root),
            )
        count += 1
    write_sync_meta(
        paths.meta_root,
        f"docs_{folder_id}",
        {"file_count": count, "local_path": str(src)},
        continuity_root=paths.continuity_root,
    )
    return {
        "folder_id": folder_id,
        "file_count": count,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


class LocalFolderSource:
    def __init__(self, entry: dict[str, Any]) -> None:
        self.id = str(entry.get("id", "local_folder"))
        self._entry = entry

    def sync(self, paths: ContinuityPaths, cfg: dict[str, Any]) -> dict[str, Any]:
        local_path = str(self._entry.get("path", "")).strip()
        if not local_path:
            return {"source_id": self.id, "type": "local_folder", "file_count": 0}
        folder_id = str(self._entry.get("docs_id", self.id))
        detail = sync_local_folder(paths, folder_id=folder_id, local_path=local_path)
        return {"source_id": self.id, "type": "local_folder", **detail}