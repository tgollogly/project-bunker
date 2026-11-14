from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from bunker.continuity.notify.outage import notify_outage
from bunker.continuity.watch.health import HealthState, WatchState


def test_notify_outage_skips_matrix_when_unconfigured(caplog) -> None:
    cfg = {
        "continuity": {
            "matrix": {"homeserver": "http://127.0.0.1:8008", "room_alias": "#outage:local"},
            "sms": {"provider": "stub"},
        }
    }
    with caplog.at_level(logging.INFO):
        with patch("bunker.continuity.notify.outage.send_matrix_message") as send:
            notify_outage(cfg, WatchState(state=HealthState.DOWN, probes={"outlook": False}))
            send.assert_not_called()
    assert any("Matrix not configured" in r.message for r in caplog.records)


def test_notify_outage_matrix_failure_is_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    monkeypatch.setenv("BUNKER_MATRIX_ACCESS_TOKEN", "tok")
    cfg = {
        "continuity": {
            "matrix": {"homeserver": "http://127.0.0.1:8008", "room_alias": "#outage:local"},
            "sms": {"provider": "stub"},
        }
    }

    def boom(**_kwargs: object) -> None:
        raise RuntimeError("homeserver down")

    with caplog.at_level(logging.WARNING):
        with patch("bunker.continuity.notify.outage.send_matrix_message", side_effect=boom):
            notify_outage(cfg, WatchState(state=HealthState.DOWN, probes={}))
    assert any("Matrix notify failed" in r.message for r in caplog.records)