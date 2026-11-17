from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from bunker.continuity.aggregate import query_all_calendar_rows
from bunker.continuity.sources.microsoft_graph import MicrosoftGraphSource
from bunker.continuity.sources.registry import run_configured_sources
from bunker.secrets.store import (
    delete_secret,
    inject_secrets_into_environ,
    list_stored_secret_names,
)


def test_registry_skips_disabled(tmp_path: Path, bunker_data_key: str) -> None:
    from conftest import continuity_paths

    paths = continuity_paths(tmp_path)
    cfg = {
        "continuity": {
            "sync_sources": [
                {"id": "off", "type": "microsoft_graph", "enabled": False},
            ]
        }
    }
    assert run_configured_sources(paths, cfg) == []


def test_registry_unknown_type(tmp_path: Path, bunker_data_key: str) -> None:
    from conftest import continuity_paths

    paths = continuity_paths(tmp_path)
    cfg = {
        "continuity": {
            "sync_sources": [{"id": "x", "type": "unknown_provider", "enabled": True}]
        }
    }
    assert run_configured_sources(paths, cfg) == []


def test_secrets_keyring_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    def _kr(name: str) -> str | None:
        return "kr" if name == "data_key" else None

    monkeypatch.setattr("bunker.secrets.store._keyring_get", _kr)
    from bunker.secrets.store import get_secret

    assert get_secret("data_key") == "kr"
    inject_secrets_into_environ(("data_key",))
    assert list_stored_secret_names()
    delete_secret("data_key")


def test_aggregate_merges_partitions(tmp_path: Path, bunker_data_key: str) -> None:
    from conftest import continuity_paths

    from bunker.continuity.parquet_io import replace_encrypted_partition_rows

    paths = continuity_paths(tmp_path)
    rows = [
        {
            "id": "e1",
            "subject": "A",
            "start": "2026-01-02T09:00:00Z",
            "end": "2026-01-02T10:00:00Z",
            "location": "x",
        }
    ]
    replace_encrypted_partition_rows(
        paths.parquet_root / "m365" / "calendar",
        rows,
        continuity_root=paths.continuity_root,
    )
    replace_encrypted_partition_rows(
        paths.parquet_root / "google" / "calendar",
        rows,
        continuity_root=paths.continuity_root,
    )
    merged = query_all_calendar_rows(
        paths,
        columns=["subject", "start", "end", "location"],
        limit=10,
    )
    assert len(merged) >= 2


def test_setup_wizard_post(
    tmp_path: Path, bunker_data_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conftest import continuity_paths
    from fastapi.testclient import TestClient

    from bunker.continuity.serve.app import create_app

    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    (root / "config" / "continuity.yaml").write_text(
        "continuity:\n  data_root: data/continuity\n", encoding="utf-8"
    )
    monkeypatch.chdir(root)
    paths = continuity_paths(root)
    app = create_app(paths, {"continuity": {"data_root": "data/continuity"}})
    client = TestClient(app)
    with patch("bunker.continuity.serve.setup_routes.install_schedule", return_value={"ok": True}):
        with patch("bunker.continuity.serve.setup_routes.set_secret"):
            with patch("bunker.continuity.serve.setup_routes.save_password_hash"):
                resp = client.post(
                    "/setup",
                    data={
                        "sources": "ical",
                        "interval_hours": "6",
                        "data_passphrase": bunker_data_key,
                        "ical_urls": "https://example.com/x.ics",
                    },
                    follow_redirects=False,
                )
    assert resp.status_code == 303


def test_google_token_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    from bunker.continuity.google.auth import GoogleOAuthSettings, GoogleTokenProvider

    class Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "tok", "expires_in": 3600}

    class Client:
        def post(self, url, data):
            return Resp()

    settings = GoogleOAuthSettings(
        client_id="id", client_secret="sec", refresh_token="refresh"
    )
    prov = GoogleTokenProvider(settings, http=Client())  # type: ignore[arg-type]
    assert prov.get_token() == "tok"


def test_schedule_darwin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from bunker.continuity.schedule.install import ScheduleSpec, install_schedule

    monkeypatch.setattr("bunker.continuity.schedule.install.platform.system", lambda: "Darwin")
    monkeypatch.setattr("bunker.continuity.schedule.install._project_root", lambda: tmp_path)
    monkeypatch.setattr("bunker.continuity.schedule.install.subprocess.run", lambda *a, **k: None)
    out = install_schedule(ScheduleSpec())
    assert out["platform"] == "darwin"


def test_schedule_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from bunker.continuity.schedule.install import ScheduleSpec, install_schedule

    monkeypatch.setattr("bunker.continuity.schedule.install.platform.system", lambda: "Windows")
    monkeypatch.setattr("bunker.continuity.schedule.install._project_root", lambda: tmp_path)
    monkeypatch.setattr("bunker.continuity.schedule.install.subprocess.run", lambda *a, **k: None)
    out = install_schedule(ScheduleSpec())
    assert out["platform"] == "windows"


def test_outage_pack_status(tmp_path: Path) -> None:
    from conftest import continuity_paths

    from bunker.continuity.outage_pack import outage_pack_status

    paths = continuity_paths(tmp_path)
    assert outage_pack_status(paths)["present"] is False


def test_microsoft_graph_sharepoint_skip(tmp_path: Path, bunker_data_key: str) -> None:
    from conftest import FakeGraph, continuity_paths

    paths = continuity_paths(tmp_path)
    cfg = {
        "continuity": {
            "sharepoint_folders": [{"id": "r", "drive_id": "", "path": "/"}],
        }
    }
    with patch("bunker.continuity.sources.microsoft_graph.build_token_provider"):
        with patch(
            "bunker.continuity.sources.microsoft_graph.HttpxGraphClient",
            return_value=FakeGraph(),
        ):
            out = MicrosoftGraphSource({"id": "m365"}).sync(paths, cfg)
    assert out["type"] == "microsoft_graph"