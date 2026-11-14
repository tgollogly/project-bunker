from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from bunker.cli import main
from bunker.continuity.config import load_continuity_config
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.seed_sample import SAMPLE_CONTACT_NAME, seed_sample_data
from bunker.continuity.serve.app import create_app
from bunker.continuity.status import continuity_status
from bunker.continuity.watch.run import watch_once
from bunker.doctor import _check_probe_hosts
from bunker.paths import BunkerPaths
from bunker.sync.package import package_airgap_sync


def test_doctor_accepts_shipped_continuity_yaml() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_continuity_config(root / "config" / "continuity.yaml")
    result = _check_probe_hosts(cfg)
    assert result.passed, result.detail
    assert "2 probe" in result.detail


def test_seed_sample_writes_real_data_root(
    project_tree: Path, bunker_data_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project_tree / "config" / "continuity.yaml").write_text(
        """
continuity:
  data_root: data/continuity
  require_encryption: true
  watch:
    probe_hosts:
      - name: outlook
        url: https://example.com
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_tree)
    paths = ContinuityPaths.from_config(
        project_tree, load_continuity_config(project_tree / "config" / "continuity.yaml")
    )
    out = seed_sample_data(paths)
    assert out["contact_name"] == SAMPLE_CONTACT_NAME
    status = continuity_status(paths)
    assert len(status) >= 3
    assert paths.parquet_root.joinpath("m365", "calendar").is_dir()


def test_cli_seed_sample_and_serve_home(
    project_tree: Path, bunker_data_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project_tree / "config" / "continuity.yaml").write_text(
        "continuity:\n  data_root: data/continuity\n  require_encryption: true\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_tree)
    runner = CliRunner()
    result = runner.invoke(main, ["continuity", "seed-sample"])
    assert result.exit_code == 0, result.output
    paths = ContinuityPaths.from_config(
        project_tree,
        {"continuity": {"data_root": "data/continuity"}},
    )
    app = create_app(paths, {"continuity": {}})
    client = TestClient(app)
    html = client.get("/").text
    assert SAMPLE_CONTACT_NAME in html


def test_sync_package_includes_continuity_after_seed(
    project_tree: Path, bunker_data_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    import stat

    os.chmod(
        project_tree / "data" / "keys" / "signing.pem",
        stat.S_IRUSR | stat.S_IWUSR,
    )
    (project_tree / "config" / "continuity.yaml").write_text(
        "continuity:\n  data_root: data/continuity\n  require_encryption: true\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_tree)
    paths_c = ContinuityPaths.from_config(
        project_tree,
        {"continuity": {"data_root": "data/continuity"}},
    )
    seed_sample_data(paths_c)
    cfg = {"bunker": {"data_root": "data", "cache_root": "cache", "sync_root": "."}}
    paths = BunkerPaths.from_config(project_tree, cfg)
    sync_dir = package_airgap_sync(paths)
    assert any(sync_dir.glob("shards/*.parquet.enc"))


def test_sync_package_empty_raises(project_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import stat

    os.chmod(
        project_tree / "data" / "keys" / "signing.pem",
        stat.S_IRUSR | stat.S_IWUSR,
    )
    monkeypatch.chdir(project_tree)
    cfg = {"bunker": {"data_root": "data", "cache_root": "cache", "sync_root": "."}}
    paths = BunkerPaths.from_config(project_tree, cfg)
    paths.ensure()
    with pytest.raises(ValueError, match="Nothing to package"):
        package_airgap_sync(paths)


def test_outage_demo_watch_down(
    project_tree: Path, bunker_data_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project_tree / "config" / "continuity.yaml").write_text(
        """
continuity:
  data_root: data/continuity
  watch:
    probe_hosts:
      - name: outlook
        url: https://x
      - name: teams
        url: https://y
    down_after_failures: 1
    degraded_after_failures: 1
    recovery_after_successes: 1
  matrix:
    homeserver: http://127.0.0.1:8008
    room_alias: '#outage:local'
  sms:
    provider: stub
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_tree)
    runner = CliRunner()
    assert runner.invoke(main, ["continuity", "seed-sample"]).exit_code == 0
    cfg = load_continuity_config(project_tree / "config" / "continuity.yaml")
    paths = ContinuityPaths.from_config(project_tree, cfg)
    out = watch_once(paths, cfg, probe_override={"outlook": False, "teams": False})
    assert out["state"] == "DOWN"
    assert list(paths.incidents_root.glob("*.json"))