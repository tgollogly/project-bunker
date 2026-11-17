from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from bunker.continuity.outage_pack import generate_outage_pack_pdf
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.schedule.install import ScheduleSpec, install_schedule
from bunker.continuity.seed_sample import seed_sample_data
from bunker.continuity.serve.app import create_app
from bunker.continuity.setup.state import SetupState, load_setup_state, save_setup_state
from bunker.continuity.sources.contacts_file import ContactsFileSource
from bunker.continuity.sources.ical_source import IcalSource
from bunker.continuity.sources.local_folder import LocalFolderSource
from bunker.secrets.store import SECRET_ENV_FALLBACK, get_secret, set_secret


def _paths(tmp_path: Path) -> ContinuityPaths:
    return ContinuityPaths.from_config(tmp_path, {"continuity": {"data_root": "data/continuity"}})


def test_secrets_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUNKER_DATA_KEY", "x")
    with patch("bunker.secrets.store._keyring_get", return_value=None):
        assert get_secret("data_key") == "x"
    set_secret("graph.client_id", "cid", prefer_keyring=False)
    assert get_secret("graph.client_id") == "cid"


def test_setup_state_roundtrip(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    state = SetupState(completed=True, selected_sources=["ical"], sync_interval_hours=12)
    save_setup_state(paths.continuity_root, state)
    loaded = load_setup_state(paths.continuity_root)
    assert loaded.completed
    assert loaded.selected_sources == ["ical"]


def test_ical_source_parses_file(tmp_path: Path, bunker_data_key: str) -> None:
    paths = _paths(tmp_path)
    ics = tmp_path / "demo.ics"
    ics.write_text(
        """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:test-1
SUMMARY:Team sync
DTSTART:20260101T100000Z
DTEND:20260101T110000Z
LOCATION:Room 1
END:VEVENT
END:VCALENDAR
""",
        encoding="utf-8",
    )
    src = IcalSource({"id": "team", "files": [str(ics)]})
    out = src.sync(paths, {"continuity": {}})
    assert out["row_count"] >= 1


def test_contacts_csv_source(tmp_path: Path, bunker_data_key: str) -> None:
    paths = _paths(tmp_path)
    csv_path = tmp_path / "people.csv"
    csv_path.write_text("name,email,mobile\nAlex,a@example.com,123\n", encoding="utf-8")
    src = ContactsFileSource({"id": "staff", "paths": [str(csv_path)]})
    out = src.sync(paths, {"continuity": {}})
    assert out["row_count"] == 1


def test_local_folder_source(tmp_path: Path, bunker_data_key: str) -> None:
    paths = _paths(tmp_path)
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "plan.md").write_text("# Plan", encoding="utf-8")
    src = LocalFolderSource({"id": "loc", "path": str(folder), "docs_id": "local"})
    out = src.sync(paths, {"continuity": {}})
    assert out["file_count"] == 1


def test_outage_pack_pdf(tmp_path: Path, bunker_data_key: str) -> None:
    paths = _paths(tmp_path)
    seed_sample_data(paths)
    out = generate_outage_pack_pdf(paths, days=14)
    assert out.is_file()
    assert out.stat().st_size > 100


def test_schedule_install_linux(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("bunker.continuity.schedule.install.platform.system", lambda: "Linux")
    monkeypatch.setattr("bunker.continuity.schedule.install._project_root", lambda: tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, check=False):
        calls.append(list(cmd))
        return MagicMock(returncode=0)

    monkeypatch.setattr("bunker.continuity.schedule.install.subprocess.run", fake_run)
    result = install_schedule(ScheduleSpec(interval_hours=4, bunker_cmd="bunker"))
    assert result["platform"] == "linux"
    assert any("bunker-continuity-sync.timer" in " ".join(c) for c in calls)


def test_setup_wizard_get(tmp_path: Path, bunker_data_key: str) -> None:
    paths = _paths(tmp_path)
    cfg = {"continuity": {"data_root": "data/continuity"}}
    app = create_app(paths, cfg)
    client = TestClient(app)
    resp = client.get("/setup")
    assert resp.status_code == 200
    assert "First-run setup" in resp.text


def test_google_workspace_mocked(
    tmp_path: Path, bunker_data_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bunker.continuity.sources.google_workspace import GoogleWorkspaceSource

    paths = _paths(tmp_path)
    monkeypatch.setenv("BUNKER_GOOGLE_ACCESS_TOKEN", "tok")

    class Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def get(self, url, **kwargs):
            if "calendar" in url:
                payload = {
                    "items": [
                        {
                            "id": "1",
                            "summary": "Meet",
                            "start": {"dateTime": "2026-01-01T09:00:00Z"},
                            "end": {"dateTime": "2026-01-01T10:00:00Z"},
                        }
                    ]
                }
                return Resp(payload)
            return Resp(
                {
                    "connections": [
                        {
                            "resourceName": "people/1",
                            "names": [{"displayName": "Sam"}],
                            "emailAddresses": [{"value": "s@x.com"}],
                            "phoneNumbers": [],
                        }
                    ]
                }
            )

    patch_path = "bunker.continuity.sources.google_workspace.httpx.Client"
    monkeypatch.setattr(patch_path, lambda **k: Client())
    src = GoogleWorkspaceSource({"id": "google"})
    out = src.sync(paths, {"continuity": {"calendar_horizon_days": 7}})
    assert out["calendar_rows"] == 1
    assert out["contact_rows"] == 1


def test_secret_env_map_covers_graph() -> None:
    assert "graph.client_id" in SECRET_ENV_FALLBACK