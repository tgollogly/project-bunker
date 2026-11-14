from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from typing import Any

MAX_UDP_PAYLOAD = 1400
DEFAULT_MAX_AGE_SECONDS = 300


def _mac(key: bytes, message: bytes) -> str:
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def pack_alert(
    message: str,
    *,
    key: bytes,
    max_message_len: int = 512,
) -> bytes:
    if len(key) < 16:
        raise ValueError("mesh key must be at least 16 bytes")
    body = message[:max_message_len]
    ts = int(time.time())
    nonce = secrets.token_hex(8)
    mac_input = f"{ts}|{nonce}|{body}".encode()
    payload: dict[str, Any] = {
        "proto": "bunker-mesh/2",
        "ts": ts,
        "nonce": nonce,
        "message": body,
        "mac": _mac(key, mac_input),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_UDP_PAYLOAD:
        raise ValueError(f"alert exceeds {MAX_UDP_PAYLOAD} bytes")
    return raw


def unpack_and_verify(
    data: bytes,
    *,
    key: bytes,
    seen_nonces: dict[str, float],
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> tuple[bool, str]:
    try:
        doc = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False, "invalid JSON payload"

    if doc.get("proto") != "bunker-mesh/2":
        return False, "unsupported proto version"

    ts = int(doc.get("ts", 0))
    nonce = str(doc.get("nonce", ""))
    message = str(doc.get("message", ""))
    mac = str(doc.get("mac", ""))
    if not nonce or not mac:
        return False, "missing nonce or mac"

    now = time.time()
    if now - ts > max_age_seconds or ts - now > 60:
        return False, "stale or future timestamp"

    if nonce in seen_nonces:
        return False, "replay detected"

    mac_input = f"{ts}|{nonce}|{message}".encode()
    expected = _mac(key, mac_input)
    if not hmac.compare_digest(expected, mac):
        return False, "invalid mac"

    seen_nonces[nonce] = now
    cutoff = now - max_age_seconds * 2
    stale = [n for n, t in seen_nonces.items() if t < cutoff]
    for n in stale:
        del seen_nonces[n]

    return True, message