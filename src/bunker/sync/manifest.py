from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bunker.crypto.signing import sign_manifest_payload
from bunker.io.atomic import atomic_write_text
from bunker.sync.bundle_format import BUNDLE_FORMAT_VERSION


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ManifestBuilder:
    sync_dir: Path
    created_by: str = "project-bunker/0.2"

    def build(
        self,
        files: list[Path],
        *,
        private_key: Ed25519PrivateKey | None = None,
        merge_hints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        for f in sorted(files, key=lambda p: p.as_posix()):
            rel = f.relative_to(self.sync_dir).as_posix()
            entries.append(
                {
                    "path": rel,
                    "bytes": f.stat().st_size,
                    "sha256": sha256_file(f),
                }
            )
        manifest: dict[str, Any] = {
            "bundle_format_version": BUNDLE_FORMAT_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": self.created_by,
            "algorithm": "sha256",
            "files": entries,
        }
        if merge_hints:
            manifest["merge_hints"] = merge_hints
        if private_key is not None:
            manifest["signature"] = sign_manifest_payload(manifest, private_key)

        manifest_path = self.sync_dir / "manifest.json"
        atomic_write_text(manifest_path, json.dumps(manifest, indent=2) + "\n")
        return manifest