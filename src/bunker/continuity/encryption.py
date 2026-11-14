from __future__ import annotations

import base64
import os
from typing import Final

from cryptography.fernet import Fernet, InvalidToken

_ENV_KEY: Final = "BUNKER_DATA_KEY"


def _fernet_from_env() -> Fernet | None:
    raw = os.environ.get(_ENV_KEY, "").strip()
    if not raw:
        return None
    if len(raw) == 44:
        key = raw.encode("ascii")
    else:
        key = base64.urlsafe_b64encode(raw.ljust(32)[:32].encode())
    return Fernet(key)


def encrypt_optional(plaintext: bytes) -> bytes:
    f = _fernet_from_env()
    if f is None:
        return plaintext
    return b"FERNET:" + f.encrypt(plaintext)


def decrypt_optional(blob: bytes) -> bytes:
    if not blob.startswith(b"FERNET:"):
        return blob
    f = _fernet_from_env()
    if f is None:
        raise RuntimeError(f"{_ENV_KEY} required to decrypt continuity data")
    try:
        return f.decrypt(blob[7:])
    except InvalidToken as exc:
        raise RuntimeError("continuity decrypt failed (wrong key?)") from exc