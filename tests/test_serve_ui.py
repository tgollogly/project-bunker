from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bunker.continuity.config import load_continuity_config
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.seed_sample import seed_sample_data
from bunker.continuity.serve.app import create_app
from bunker.continuity.watch.health import (
    HealthState,
    WatchState,
    save_watch_state,
)


def _app_with_seed(tmp_path: Path, bunker_data_key: str) -> tuple[TestClient, ContinuityPaths]:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "continuity.yaml").write_text(
        "continuity:\n  data_root: data/continuity\n  require_encryption: true\n",
        encoding="utf-8",
    )
    cfg = load_continuity_config(tmp_path / "config" / "continuity.yaml")
    paths = ContinuityPaths.from_config(tmp_path, cfg)
    seed_sample_data(paths)
    app = create_app(paths, {"continuity": {}})
    return TestClient(app), paths


def _set_watch(
    paths: ContinuityPaths,
    state: HealthState,
    probes: dict[str, bool] | None = None,
) -> None:
    save_watch_state(
        paths.state_file,
        WatchState(
            state=state,
            probes=probes or {"outlook": state == HealthState.OK, "teams": state != HealthState.OK},
            updated_at=1_700_000_000.0,
        ),
    )


@pytest.mark.parametrize(
    ("state", "phrase", "banner_class"),
    [
        (HealthState.OK, "Cloud services look reachable", "status-banner--ok"),
        (HealthState.DEGRADED, "Cloud services may be degraded", "status-banner--degraded"),
        (HealthState.DOWN, "Cloud appears DOWN", "status-banner--down"),
    ],
)
def test_status_banner_states(
    tmp_path: Path,
    bunker_data_key: str,
    state: HealthState,
    phrase: str,
    banner_class: str,
) -> None:
    client, paths = _app_with_seed(tmp_path, bunker_data_key)
    _set_watch(paths, state)
    html = client.get("/").text
    assert phrase in html
    assert banner_class in html
    assert "status-banner__headline" in html
    if state == HealthState.DOWN:
        assert 'role="alert"' in html
    assert "/static/continuity.css" in html


def test_home_dashboard_populated(tmp_path: Path, bunker_data_key: str) -> None:
    client, paths = _app_with_seed(tmp_path, bunker_data_key)
    _set_watch(paths, HealthState.DOWN, {"outlook": False, "teams": False})
    html = client.get("/").text
    assert "SAMPLE DATA" in html or "Sample data" in html
    assert "Sam Sampleton" in html
    assert "m365_calendar" in html or "Team stand-up" in html or "[SAMPLE]" in html
    assert "outage-checklist" in html.lower() or "Runbooks" in html


def test_status_page_sync_table(tmp_path: Path, bunker_data_key: str) -> None:
    client, paths = _app_with_seed(tmp_path, bunker_data_key)
    _set_watch(paths, HealthState.DOWN, {"outlook": False, "teams": False})
    html = client.get("/status").text
    assert "m365_calendar" in html
    assert "m365_contacts" in html
    assert "dot--down" in html or "unreachable" in html


def test_contacts_search_query(tmp_path: Path, bunker_data_key: str) -> None:
    client, _paths = _app_with_seed(tmp_path, bunker_data_key)
    html = client.get("/contacts?q=Sam").text
    assert "Sam Sampleton" in html
    assert "Alex Example" not in html


def test_static_css_served(tmp_path: Path, bunker_data_key: str) -> None:
    client, _ = _app_with_seed(tmp_path, bunker_data_key)
    resp = client.get("/static/continuity.css")
    assert resp.status_code == 200
    assert "--navy: #0f1b2d" in resp.text