from pathlib import Path
from unittest.mock import patch

from conftest import FakeGraph
from conftest import continuity_paths as _paths
from fastapi.testclient import TestClient

from bunker.continuity.encryption import decrypt_optional, encrypt_optional
from bunker.continuity.graph.sync_calendars import sync_calendars
from bunker.continuity.graph.sync_contacts import sync_contacts
from bunker.continuity.meta import write_sync_meta
from bunker.continuity.notify.sms import StubSmsProvider
from bunker.continuity.serve.app import create_app
from bunker.continuity.status import continuity_status
from bunker.continuity.watch.health import (
    HealthState,
    WatchConfig,
    evaluate_watch,
    load_watch_state,
)
from bunker.continuity.watch.run import watch_once


def test_encryption_roundtrip(tmp_path: Path, bunker_data_key: str) -> None:
    paths = _paths(tmp_path)
    blob = encrypt_optional(b"secret", continuity_root=paths.continuity_root)
    assert decrypt_optional(blob, continuity_root=paths.continuity_root) == b"secret"


def test_graph_calendar_and_contacts_sync(tmp_path: Path, bunker_data_key: str) -> None:
    paths = _paths(tmp_path)
    client = FakeGraph()
    sync_calendars(paths, client, user="me", horizon_days=7)
    sync_contacts(paths, client, user="me")
    status = continuity_status(paths)
    ids = {s["source_id"] for s in status}
    assert "m365_calendar" in ids
    assert "m365_contacts" in ids


def test_watch_hysteresis_to_down(tmp_path: Path) -> None:
    state_file = tmp_path / "watch.json"
    cfg = WatchConfig(
        probe_hosts=[{"name": "outlook", "url": "https://example.com"}],
        degraded_after_failures=2,
        down_after_failures=3,
        recovery_after_successes=2,
    )
    prev = load_watch_state(state_file)
    for _ in range(3):
        prev = evaluate_watch(
            cfg,
            probe_results={"outlook": False},
            graph_reachable=None,
            graph_service_unhealthy=False,
            prev=prev,
        )
    assert prev.state == HealthState.DOWN


def test_watch_once_records_incident_on_down(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    cfg = {
        "continuity": {
            "watch": {
                "probe_hosts": [{"name": "outlook", "url": "https://x"}],
                "down_after_failures": 1,
                "degraded_after_failures": 1,
                "recovery_after_successes": 1,
            },
            "matrix": {"homeserver": "http://127.0.0.1:8008", "room_alias": "#outage:local"},
            "sms": {"provider": "stub"},
        }
    }
    # Prime state as OK then force failures
    with patch("bunker.continuity.watch.run.notify_outage") as notify:
        result = {"state": "OK"}
        for _ in range(3):
            result = watch_once(
                paths,
                cfg,
                probe_override={"outlook": False, "teams": False},
            )
        assert result["state"] == "DOWN"
        notify.assert_called()


def test_serve_offline_pages(tmp_path: Path, bunker_data_key: str) -> None:
    paths = _paths(tmp_path)
    write_sync_meta(paths.meta_root, "m365_calendar", continuity_root=paths.continuity_root)
    app = create_app(paths, {"continuity": {"element_url": "http://local/element"}})
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/status").status_code == 200
    assert client.get("/api/status").json()["watch"]


def test_stub_sms() -> None:
    sms = StubSmsProvider()
    sms.send("hello")
    assert sms.last_message == "hello"