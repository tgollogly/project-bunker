import time

import pytest

from bunker.comms.mesh_auth import pack_alert, unpack_and_verify

KEY = b"test-mesh-key-16b!"


def test_udp_alert_roundtrip() -> None:
    seen: dict[str, float] = {}
    raw = pack_alert("sync ready", key=KEY)
    ok, msg = unpack_and_verify(raw, key=KEY, seen_nonces=seen)
    assert ok is True
    assert msg == "sync ready"


def test_udp_replay_rejected() -> None:
    seen: dict[str, float] = {}
    raw = pack_alert("once", key=KEY)
    assert unpack_and_verify(raw, key=KEY, seen_nonces=seen)[0]
    assert unpack_and_verify(raw, key=KEY, seen_nonces=seen)[0] is False


def test_udp_stale_timestamp() -> None:
    seen: dict[str, float] = {}
    raw = pack_alert("old", key=KEY)
    # Tamper ts to old value
    import json

    doc = json.loads(raw.decode())
    doc["ts"] = int(time.time()) - 99999
    doc["message"] = "old"
    from bunker.comms.mesh_auth import _mac

    doc["mac"] = _mac(KEY, f"{doc['ts']}|{doc['nonce']}|{doc['message']}".encode())
    bad = json.dumps(doc, separators=(",", ":")).encode()
    ok, reason = unpack_and_verify(bad, key=KEY, seen_nonces=seen, max_age_seconds=60)
    assert ok is False
    assert "stale" in reason


def test_pack_requires_key_length() -> None:
    with pytest.raises(ValueError):
        pack_alert("x", key=b"short")