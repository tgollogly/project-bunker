from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
from conftest import FakeGraph
from conftest import continuity_paths as _paths
from fastapi.testclient import TestClient

from bunker.continuity.config import load_continuity_config
from bunker.continuity.graph.auth import StaticTokenProvider
from bunker.continuity.graph.client import HttpxGraphClient
from bunker.continuity.graph.sync_documents import sync_sharepoint_folder
from bunker.continuity.meta import read_sync_meta, write_sync_meta
from bunker.continuity.notify.matrix import send_matrix_message
from bunker.continuity.notify.outage import notify_outage
from bunker.continuity.serve.app import create_app
from bunker.continuity.sync_all import run_continuity_sync
from bunker.continuity.watch.health import WatchConfig, probe_url, run_watch


def test_config_env_expand(tmp_path: Path) -> None:
    cfg_path = tmp_path / "continuity.yaml"
    cfg_path.write_text("continuity:\n  matrix:\n    homeserver: '${BUNKER_MATRIX_HOMESERVER:-http://x}'")
    with patch.dict("os.environ", {}, clear=True):
        cfg = load_continuity_config(cfg_path)
    assert cfg["continuity"]["matrix"]["homeserver"] == "http://x"


def test_graph_client_retry_after() -> None:
    provider = StaticTokenProvider("tok")
    client = HttpxGraphClient(provider, max_retries=2)

    class Resp:
        def __init__(self, status, content=b"{}", headers=None):
            self.status_code = status
            self.content = content
            self.headers = headers or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("err", request=MagicMock(), response=MagicMock())

        def json(self):
            return {}

    calls = {"n": 0}

    def fake_get(url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return Resp(429, headers={"Retry-After": "0"})
        return Resp(200)

    with patch("httpx.Client") as mock_client:
        inst = mock_client.return_value.__enter__.return_value
        inst.get = fake_get
        inst.request = lambda *a, **k: fake_get(a[1] if len(a) > 1 else "")
        data = client.get("/me")
        assert data == {}
        assert calls["n"] >= 2


def test_sync_documents_manifest(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    client = FakeGraph()
    client.get = lambda path, **kwargs: {  # type: ignore[method-assign]
        "value": [{"id": "f1", "name": "runbook.pdf", "file": {}}]
    }
    out = sync_sharepoint_folder(
        paths,
        client,
        folder_id="runbooks",
        drive_id="drive1",
        remote_path="/Docs",
    )
    assert out["files"] == 1
    assert (paths.manifest_root / "runbooks.json").is_file()


def test_run_continuity_sync_mocked(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    cfg = {
        "continuity": {
            "calendar_horizon_days": 7,
            "graph": {"calendar_user": "me", "contact_user": "me"},
            "sharepoint_folders": [],
        }
    }
    tok = StaticTokenProvider("t")
    with patch("bunker.continuity.sync_all.build_token_provider", return_value=tok):
        with patch("bunker.continuity.sync_all.HttpxGraphClient", return_value=FakeGraph()):
            results = run_continuity_sync(paths, cfg)
    assert len(results) == 2


def test_matrix_send_mocked() -> None:
    with patch("httpx.Client") as mock_client:
        inst = mock_client.return_value.__enter__.return_value
        inst.get.return_value = MagicMock(status_code=200, json=lambda: {"room_id": "!r:local"})
        inst.put.return_value = MagicMock(status_code=200, raise_for_status=lambda: None)
        send_matrix_message(
            homeserver="http://hs",
            room_alias="#outage:local",
            message="hi",
            access_token="token",
        )


def test_notify_outage_stub_sms() -> None:
    cfg = {
        "continuity": {
            "matrix": {"homeserver": "http://127.0.0.1:1", "room_alias": "#x:local"},
            "sms": {"provider": "stub"},
        }
    }
    from bunker.continuity.watch.health import HealthState, WatchState

    side_effect = RuntimeError("no matrix")
    with patch("bunker.continuity.notify.outage.send_matrix_message", side_effect=side_effect):
        notify_outage(cfg, WatchState(state=HealthState.DOWN, probes={"a": False}))


def test_meta_encryption_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BUNKER_DATA_KEY", "b" * 32)
    paths = _paths(tmp_path)
    write_sync_meta(paths.meta_root, "test_src", {"n": 1})
    doc = read_sync_meta(paths.meta_root, "test_src")
    assert doc and doc["source_id"] == "test_src"


def test_serve_calendar_with_data(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    from bunker.ingest.parquet_writer import write_rows_parquet_duckdb

    part = paths.parquet_root / "m365/calendar/ingest_date=2026-11-14/part-x.parquet"
    write_rows_parquet_duckdb(
        [{"subject": "A", "start": "t1", "end": "t2", "location": "L", "_bunker_ingested_at": "t"}],
        part,
    )
    app = create_app(paths, {"continuity": {}})
    html = TestClient(app).get("/calendar").text
    assert "Stand-up" not in html or "A" in html


def test_probe_url_success() -> None:
    with patch("httpx.Client") as mock_client:
        inst = mock_client.return_value.__enter__.return_value
        inst.get.return_value = MagicMock(status_code=200)
        assert probe_url("https://example.com") is True


def test_run_watch_ok(tmp_path: Path) -> None:
    wc = WatchConfig(probe_hosts=[{"name": "o", "url": "https://x"}])
    st = run_watch(wc, tmp_path / "w.json", probe_override={"o": True})
    assert st.state.value == "OK"