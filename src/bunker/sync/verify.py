from __future__ import annotations

import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from bunker.crypto.signing import verify_manifest_signature
from bunker.sync.bundle_format import MANIFEST_SIDECAR_NAMES, SUPPORTED_BUNDLE_VERSIONS
from bunker.sync.manifest import sha256_file


def _listed_paths(manifest: dict) -> set[str]:
    return {entry["path"] for entry in manifest.get("files", [])}


def _walk_files(sync_dir: Path) -> set[str]:
    found: set[str] = set()
    for p in sync_dir.rglob("*"):
        if p.is_file():
            found.add(p.relative_to(sync_dir).as_posix())
    return found


def verify_sync_folder(
    sync_dir: Path,
    *,
    public_key: Ed25519PublicKey | None = None,
    require_signature: bool = True,
) -> tuple[bool, list[str]]:
    """Verify bundle hashes, signature, version, and no extra files."""
    manifest_path = sync_dir / "manifest.json"
    if not manifest_path.is_file():
        return False, ["missing manifest.json"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    errors: list[str] = []
    version = manifest.get("bundle_format_version", manifest.get("version", 1))
    if version not in SUPPORTED_BUNDLE_VERSIONS:
        errors.append(f"unsupported bundle_format_version: {version}")

    listed = _listed_paths(manifest)
    on_disk = _walk_files(sync_dir)
    allowed_extra = MANIFEST_SIDECAR_NAMES
    extra = on_disk - listed - allowed_extra
    if extra:
        errors.append(f"unlisted files in bundle: {', '.join(sorted(extra))}")

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

    sig = manifest.get("signature")
    if require_signature:
        if not sig:
            errors.append("missing manifest signature")
        elif public_key is None:
            errors.append("missing trusted public key for signature verification")
        elif not verify_manifest_signature(manifest, sig, public_key):
            errors.append("invalid manifest signature")
    elif sig and public_key is not None:
        if not verify_manifest_signature(manifest, sig, public_key):
            errors.append("invalid manifest signature")

    return len(errors) == 0, errors