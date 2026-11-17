from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from bunker.continuity.graph.sync_calendars import sync_calendars
from bunker.continuity.sync_all import run_continuity_sync
from bunker.continuity.watch.health import (
    ProbeState,
    parse_health_overviews,
    probe_url,
    unhealthy_watched_services,
)
from bunker.doctor import _check_graph_env, _check_probe_hosts


def test_sync_all_skips_folder_without_drive_id(
    tmp_path: Path, bunker_data_key: str
) -> None:
    from conftest import FakeGraph, continuity_paths

    paths = continuity_paths(tmp_path)
    cfg = {
        "continuity": {
            "sharepoint_folders": [{"id": "runbooks", "path": "/", "drive_id": ""}],
        }
    }
    with patch("bunker.continuity.sources.microsoft_graph.HttpxGraphClient") as mock_client:
        mock_client.return_value = FakeGraph()
        with patch("bunker.continuity.sources.microsoft_graph.build_token_provider"):
            with patch("bunker.continuity.sources.microsoft_graph.sync_calendars") as sc:
                with patch("bunker.continuity.sources.microsoft_graph.sync_contacts") as sct:
                    sc.return_value = {"source_id": "m365_calendar"}
                    sct.return_value = {"source_id": "m365_contacts"}
                    with patch("bunker.continuity.sync_all.generate_outage_pack_pdf"):
                        out = run_continuity_sync(paths, cfg)
    assert len(out) == 1


def test_sync_all_raises_when_graph_auth_fails(
    tmp_path: Path, bunker_data_key: str
) -> None:
    from conftest import continuity_paths

    paths = continuity_paths(tmp_path)
    cfg = {"continuity": {}}
    with patch(
        "bunker.continuity.sources.microsoft_graph.HttpxGraphClient",
        side_effect=RuntimeError("no auth"),
    ):
        with patch("bunker.continuity.sources.microsoft_graph.build_token_provider"):
            with pytest.raises(RuntimeError, match="no auth"):
                run_continuity_sync(paths, cfg)


def test_probe_url_treats_401_as_up(monkeypatch: pytest.MonkeyPatch) -> None:
    class Resp:
        status_code = 401

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def get(self, url):
            return Resp()

    monkeypatch.setattr(httpx, "Client", lambda **k: Client())
    assert probe_url("https://example.com") == ProbeState.UP


def test_parse_health_overviews_invalid() -> None:
    assert parse_health_overviews({}) == []
    assert parse_health_overviews({"value": "nope"}) == []


def test_unhealthy_watched_services_flags_degraded() -> None:
    rows = [{"service": "Exchange Online", "status": "serviceDegradation"}]
    bad = unhealthy_watched_services(rows, ["Exchange Online"])
    assert "Exchange Online" in bad


def test_doctor_graph_env_and_probes() -> None:
    assert _check_graph_env().passed is False
    assert _check_probe_hosts({"continuity": {"probe_hosts": []}}).passed is False
    ok = _check_probe_hosts(
        {"continuity": {"watch": {"probe_hosts": [{"name": "a", "url": "https://x"}]}}}
    )
    assert ok.passed


def test_calendar_sync_writes_encrypted_parquet(
    tmp_path: Path, bunker_data_key: str
) -> None:
    from conftest import FakeGraph, continuity_paths

    paths = continuity_paths(tmp_path)
    sync_calendars(paths, FakeGraph(), user="me", horizon_days=3)
    assert list(paths.continuity_root.rglob("*.parquet.enc"))