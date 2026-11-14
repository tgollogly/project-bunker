from __future__ import annotations

from pathlib import Path

from bunker.continuity.encryption import decrypt_at_rest, encrypt_at_rest
from bunker.io.atomic import atomic_write_bytes

ENCRYPTED_DOC_SUFFIX = ".enc"


def encrypted_doc_path(dest: Path) -> Path:
    if dest.suffix == ENCRYPTED_DOC_SUFFIX:
        return dest
    return dest.with_suffix(dest.suffix + ENCRYPTED_DOC_SUFFIX)


def write_encrypted_file(dest: Path, plaintext: bytes, *, continuity_root: Path) -> Path:
    dest = encrypted_doc_path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(dest, encrypt_at_rest(plaintext, continuity_root=continuity_root))
    return dest


def read_encrypted_file(path: Path, *, continuity_root: Path) -> bytes:
    return decrypt_at_rest(path.read_bytes(), continuity_root=continuity_root)


def iter_encrypted_doc_files(docs_root: Path) -> list[Path]:
    if not docs_root.is_dir():
        return []
    suffix = ENCRYPTED_DOC_SUFFIX
    return sorted(
        p for p in docs_root.rglob("*") if p.is_file() and p.name.endswith(suffix)
    )