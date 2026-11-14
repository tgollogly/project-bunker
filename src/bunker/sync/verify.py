from __future__ import annotations

import json
from pathlib import Path

from bunker.sync.manifest import sha256_file


def verify_sync_folder(sync_dir: Path) -> tuple[bool, list[str]]:
    """Verify manifest.json SHA-256 entries for an air-gap bundle."""
    manifest_path = sync_dir / "manifest.json"
    if not manifest_path.is_file():
        return False, ["missing manifest.json"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for entry in manifest.get("files", []):
        rel = entry["path"]
        expected = entry["sha256"]
        target = sync_dir / rel
        if not target.is_file():
            errors.append(f"missing file: {rel}")
            continue
        actual = sha256_file(target)
        if actual != expected:
            errors.append(f"hash mismatch: {rel}")
    return len(errors) == 0, errors