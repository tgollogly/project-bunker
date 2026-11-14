import os
from unittest.mock import patch

from bunker.comms.udp_broadcast import send_alert


def test_send_alert_requires_mesh_key() -> None:
    with patch.dict(os.environ, {}, clear=True):
        try:
            send_alert("hi")
            raise AssertionError("expected failure")
        except RuntimeError as exc:
            assert "BUNKER_MESH_KEY" in str(exc)


def test_send_alert_with_key() -> None:
    with patch.dict(os.environ, {"BUNKER_MESH_KEY": "sixteen-byte-key!!"}):
        with patch("socket.socket") as mock_sock:
            inst = mock_sock.return_value
            send_alert("sync ready", port=41567)
            inst.sendto.assert_called_once()