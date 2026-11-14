from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path
from typing import Final

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

_ENV_KEY: Final = "BUNKER_DATA_KEY"
_ENV_NEW_KEY: Final = "BUNKER_DATA_KEY_NEW"
_PREFIX: Final = b"FERNET:"
_SALT_NAME: Final = ".fernet_salt"
_SCRYPT_N: Final = 2**15
_SCRYPT_R: Final = 8
_SCRYPT_P: Final = 1


class EncryptionRequiredError(RuntimeError):
    """Raised when continuity requires encryption but no key is configured."""


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
    path.write_bytes(salt)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return salt


def fernet_from_material(*, continuity_root: Path | None = None) -> Fernet | None:
    raw = os.environ.get(_ENV_KEY, "").strip()
    if not raw:
        return None
    if _is_raw_fernet_key(raw):
        return Fernet(raw.encode("ascii"))
    if continuity_root is None:
        raise RuntimeError("passphrase BUNKER_DATA_KEY requires continuity data root for salt")
    salt = load_or_create_salt(continuity_root)
    return Fernet(_fernet_bytes_from_passphrase(raw, salt))


def require_encryption_config(cfg: dict) -> bool:
    cont = cfg.get("continuity", {})
    return bool(cont.get("require_encryption", True))


def encryption_available(continuity_root: Path) -> bool:
    return os.environ.get(_ENV_KEY, "").strip() != ""


def ensure_encryption_key(cfg: dict, continuity_root: Path) -> None:
    if require_encryption_config(cfg) and not encryption_available(continuity_root):
        raise EncryptionRequiredError(
            "continuity require_encryption is enabled but BUNKER_DATA_KEY is not set "
            "(use a 44-character url-safe Fernet key or a passphrase with per-site salt)"
        )


def encrypt_at_rest(plaintext: bytes, *, continuity_root: Path) -> bytes:
    f = fernet_from_material(continuity_root=continuity_root)
    if f is None:
        raise EncryptionRequiredError("BUNKER_DATA_KEY required to encrypt continuity data")
    return _PREFIX + f.encrypt(plaintext)


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


def encrypt_optional(plaintext: bytes, *, continuity_root: Path) -> bytes:
    return encrypt_at_rest(plaintext, continuity_root=continuity_root)


def decrypt_optional(blob: bytes, *, continuity_root: Path) -> bytes:
    return decrypt_at_rest(blob, continuity_root=continuity_root)


def rekey_tree(continuity_root: Path, *, old_root: Path | None = None) -> int:
    """Re-encrypt all FERNET blobs under continuity_root using BUNKER_DATA_KEY_NEW."""
    new_raw = os.environ.get(_ENV_NEW_KEY, "").strip()
    if not new_raw:
        raise RuntimeError(f"{_ENV_NEW_KEY} must be set for rekey")
    old_key = os.environ.get(_ENV_KEY, "").strip()
    if not old_key:
        raise RuntimeError(f"{_ENV_KEY} must be set (current key) for rekey")

    count = 0
    for path in continuity_root.rglob("*"):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if not raw.startswith(_PREFIX):
            continue
        plain = decrypt_at_rest(raw, continuity_root=old_root or continuity_root)
        os.environ[_ENV_KEY] = new_raw
        try:
            new_blob = encrypt_at_rest(plain, continuity_root=continuity_root)
        finally:
            os.environ[_ENV_KEY] = old_key
        path.write_bytes(new_blob)
        count += 1
    os.environ[_ENV_KEY] = new_raw
    return count