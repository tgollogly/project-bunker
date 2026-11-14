from unittest.mock import patch

from bunker.comms import udp_broadcast as udp


def test_udp_main_send_branch() -> None:
    with patch.object(udp, "send_alert") as mock_send:
        assert udp.main(["send", "hello", "--port", "9"]) == 0
        mock_send.assert_called_once_with("hello", port=9)