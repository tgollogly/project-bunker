from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ManifestBuilder:
    sync_dir: Path
    created_by: str = "project-bunker/0.1"

    def build(self, files: list[Path]) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        for f in sorted(files, key=lambda p: p.name):
            rel = f.relative_to(self.sync_dir).as_posix()
            entries.append(
                {
                    "path": rel,
                    "bytes": f.stat().st_size,
                    "sha256": sha256_file(f),
                }
            )
        manifest: dict[str, Any] = {
            "version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": self.created_by,
            "algorithm": "sha256",
            "files": entries,
        }
        manifest_path = self.sync_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return manifest