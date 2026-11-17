from __future__ import annotations

import base64
import os
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Final

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from bunker.io.atomic import atomic_write_bytes
from bunker.secrets.store import get_secret

_ENV_KEY: Final = "BUNKER_DATA_KEY"
_ENV_NEW_KEY: Final = "BUNKER_DATA_KEY_NEW"
_PREFIX: Final = b"FERNET:"
_SALT_NAME: Final = ".fernet_salt"
_SCRYPT_N: Final = 2**15
_SCRYPT_R: Final = 8
_SCRYPT_P: Final = 1


class EncryptionRequiredError(RuntimeError):
    """Raised when continuity requires encryption but no key is configured."""


class RekeyAbortError(RuntimeError):
    """Raised when rekey aborts mid-flight (used in tests)."""


def _is_raw_fernet_key(raw: str) -> bool:
    if len(raw) != 44:
        return False
    try:
        Fernet(raw.encode("ascii"))
        return True
    except (ValueError, TypeError):
        return False


def _fernet_bytes_from_passphrase(passphrase: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    key = kdf.derive(passphrase.encode("utf-8"))
    return base64.urlsafe_b64encode(key)


def load_or_create_salt(continuity_root: Path) -> bytes:
    path = continuity_root / _SALT_NAME
    if path.is_file():
        return path.read_bytes()
    salt = secrets.token_bytes(16)
    continuity_root.mkdir(parents=True, exist_ok=True)
    atomic_write_private(path, salt)
    return salt


def _chmod_private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def atomic_write_private(path: Path, data: bytes) -> None:
    atomic_write_bytes(path, data)
    _chmod_private(path)


def fernet_from_raw(raw: str, *, continuity_root: Path, salt: bytes | None = None) -> Fernet:
    if _is_raw_fernet_key(raw):
        return Fernet(raw.encode("ascii"))
    if salt is None:
        salt = load_or_create_salt(continuity_root)
    return Fernet(_fernet_bytes_from_passphrase(raw, salt))


def _data_key_material() -> str:
    return (get_secret("data_key") or os.environ.get(_ENV_KEY, "")).strip()


def fernet_from_material(*, continuity_root: Path | None = None) -> Fernet | None:
    raw = _data_key_material()
    if not raw:
        return None
    if continuity_root is None and not _is_raw_fernet_key(raw):
        raise RuntimeError("passphrase BUNKER_DATA_KEY requires continuity data root for salt")
    root = continuity_root or Path(".")
    return fernet_from_raw(raw, continuity_root=root)


def require_encryption_config(cfg: dict) -> bool:
    cont = cfg.get("continuity", {})
    return bool(cont.get("require_encryption", True))


def encryption_available(continuity_root: Path) -> bool:
    _ = continuity_root
    return _data_key_material() != ""


def ensure_encryption_key(cfg: dict, continuity_root: Path) -> None:
    if require_encryption_config(cfg) and not encryption_available(continuity_root):
        raise EncryptionRequiredError(
            "continuity require_encryption is enabled but BUNKER_DATA_KEY is not set "
            "(use a 44-character url-safe Fernet key or a passphrase with per-site salt)"
        )


def encrypt_blob(plaintext: bytes, fernet: Fernet) -> bytes:
    return _PREFIX + fernet.encrypt(plaintext)


def encrypt_at_rest(plaintext: bytes, *, continuity_root: Path) -> bytes:
    f = fernet_from_material(continuity_root=continuity_root)
    if f is None:
        raise EncryptionRequiredError("BUNKER_DATA_KEY required to encrypt continuity data")
    return encrypt_blob(plaintext, f)


def decrypt_at_rest(blob: bytes, *, continuity_root: Path) -> bytes:
    if not blob.startswith(_PREFIX):
        raise RuntimeError("continuity blob is not encrypted (expected FERNET prefix)")
    f = fernet_from_material(continuity_root=continuity_root)
    if f is None:
        raise RuntimeError(f"{_ENV_KEY} required to decrypt continuity data")
    try:
        return f.decrypt(blob[len(_PREFIX) :])
    except InvalidToken as exc:
        raise RuntimeError("continuity decrypt failed (wrong key?)") from exc


def decrypt_with_fernet(blob: bytes, fernet: Fernet) -> bytes:
    if not blob.startswith(_PREFIX):
        raise RuntimeError("continuity blob is not encrypted (expected FERNET prefix)")
    try:
        return fernet.decrypt(blob[len(_PREFIX) :])
    except InvalidToken as exc:
        raise RuntimeError("continuity decrypt failed (wrong key?)") from exc


def encrypt_optional(plaintext: bytes, *, continuity_root: Path) -> bytes:
    return encrypt_at_rest(plaintext, continuity_root=continuity_root)


def decrypt_optional(blob: bytes, *, continuity_root: Path) -> bytes:
    return decrypt_at_rest(blob, continuity_root=continuity_root)


def _encrypted_paths(continuity_root: Path) -> list[Path]:
    out: list[Path] = []
    for path in continuity_root.rglob("*"):
        if not path.is_file():
            continue
        if path.name == _SALT_NAME:
            continue
        raw = path.read_bytes()
        if raw.startswith(_PREFIX):
            out.append(path)
    return sorted(out)


def rekey_tree(
    continuity_root: Path,
    *,
    old_root: Path | None = None,
    on_file_rekeyed: Callable[[Path, int, int], None] | None = None,
) -> int:
    """Re-encrypt all FERNET blobs under continuity_root using BUNKER_DATA_KEY_NEW."""

    new_raw = os.environ.get(_ENV_NEW_KEY, "").strip()
    if not new_raw:
        raise RuntimeError(f"{_ENV_NEW_KEY} must be set for rekey")
    old_key = os.environ.get(_ENV_KEY, "").strip()
    if not old_key:
        raise RuntimeError(f"{_ENV_KEY} must be set (current key) for rekey")

    root = old_root or continuity_root
    old_fernet = fernet_from_raw(old_key, continuity_root=root)
    new_salt: bytes | None = None
    if not _is_raw_fernet_key(new_raw):
        new_salt = secrets.token_bytes(16)
        new_fernet = fernet_from_raw(new_raw, continuity_root=continuity_root, salt=new_salt)
    else:
        new_fernet = fernet_from_raw(new_raw, continuity_root=continuity_root)

    paths = _encrypted_paths(continuity_root)
    plaintexts: dict[Path, bytes] = {}
    for path in paths:
        blob = path.read_bytes()
        plaintexts[path] = decrypt_with_fernet(blob, old_fernet)

    total = len(paths)
    for index, path in enumerate(paths, start=1):
        new_blob = encrypt_blob(plaintexts[path], new_fernet)
        atomic_write_bytes(path, new_blob)
        if on_file_rekeyed is not None:
            on_file_rekeyed(path, index, total)

    if new_salt is not None:
        atomic_write_private(continuity_root / _SALT_NAME, new_salt)

    return total