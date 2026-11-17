from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from bunker.continuity.sync_all import run_continuity_sync
from bunker.continuity.watch.health import ProbeState, evaluate_watch, probe_url
from bunker.doctor import (
    _check_continuity_encryption,
    _check_graph_reachability,
    _check_signing_key,
    _check_sources_config,
    run_doctor,
)
from bunker.paths import BunkerPaths
from bunker.sync.package import _merge_hints_from_config


def test_doctor_missing_sources(tmp_path: Path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    assert _check_sources_config(root).passed is False


def test_doctor_bad_sources_yaml(tmp_path: Path) -> None:
    root = tmp_path / "r"
    (root / "config").mkdir(parents=True)
    (root / "config" / "sources.yaml").write_text("not: [valid", encoding="utf-8")
    assert _check_sources_config(root).passed is False


def test_doctor_encryption_required(tmp_path: Path) -> None:
    from conftest import continuity_paths

    paths = continuity_paths(tmp_path)
    cfg = {"continuity": {"require_encryption": True}}
    assert _check_continuity_encryption(paths, cfg).passed is False


def test_doctor_signing_key_missing(tmp_path: Path) -> None:
    paths = BunkerPaths.from_config(
        tmp_path,
        {"bunker": {"data_root": "data", "cache_root": "cache", "sync_root": "."}},
    )
    assert _check_signing_key(paths).passed is False


def test_doctor_graph_reachability_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUNKER_GRAPH_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("BUNKER_GRAPH_TENANT_ID", raising=False)
    r = _check_graph_reachability()
    assert r.passed and "skipped" in r.detail


def test_doctor_graph_reachability_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUNKER_GRAPH_ACCESS_TOKEN", "x")

    class BadClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def get(self, url):
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "Client", lambda **k: BadClient())
    assert _check_graph_reachability().passed is False


def test_probe_url_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Resp:
        status_code = 503

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def get(self, url):
            return Resp()

    monkeypatch.setattr(httpx, "Client", lambda **k: Client())
    assert probe_url("https://example.com") == ProbeState.DOWN


def test_verify_missing_manifest(tmp_path: Path) -> None:
    from bunker.sync.verify import verify_sync_folder

    ok, errs = verify_sync_folder(tmp_path / "empty")
    assert not ok
    assert "missing manifest.json" in errs[0]


def test_verify_bad_bundle_version(tmp_path: Path, signing_keys: tuple[Path, Path]) -> None:
    import json

    from bunker.crypto.signing import load_private_key
    from bunker.sync.manifest import ManifestBuilder
    from bunker.sync.verify import verify_sync_folder

    sync = tmp_path / "bundle"
    sync.mkdir()
    f = sync / "data.parquet"
    f.write_bytes(b"PAR1")
    priv, pub = signing_keys
    ManifestBuilder(sync).build([f], private_key=load_private_key(priv))
    manifest = json.loads((sync / "manifest.json").read_text(encoding="utf-8"))
    manifest["bundle_format_version"] = 99
    (sync / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    from bunker.crypto.signing import load_public_key

    ok, errs = verify_sync_folder(sync, public_key=load_public_key(pub), require_signature=True)
    assert not ok
    assert any("unsupported" in e for e in errs)


def test_probe_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class BadClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def get(self, url):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "Client", lambda **k: BadClient())
    assert probe_url("https://example.com") == ProbeState.DOWN


def test_evaluate_watch_recovery() -> None:
    from bunker.continuity.watch.health import HealthState, WatchConfig, WatchState

    cfg = WatchConfig(probe_hosts=[], recovery_after_successes=2)
    prev = WatchState(state=HealthState.DOWN, consecutive_failures=3)
    nxt = evaluate_watch(
        cfg,
        probe_results={"a": True},
        graph_reachable=None,
        graph_service_unhealthy=False,
        prev=prev,
    )
    assert nxt.consecutive_successes == 1
    assert nxt.consecutive_failures == 0


def test_sync_all_sharepoint_error_path(
    tmp_path: Path, bunker_data_key: str
) -> None:
    from conftest import FakeGraph, continuity_paths

    paths = continuity_paths(tmp_path)
    cfg = {
        "continuity": {
            "sharepoint_folders": [
                {"id": "runbooks", "drive_id": "drv", "path": "/"},
            ],
        }
    }
    with patch("bunker.continuity.sources.microsoft_graph.HttpxGraphClient") as mock_client:
        mock_client.return_value = FakeGraph()
        with patch("bunker.continuity.sources.microsoft_graph.build_token_provider"):
            with patch("bunker.continuity.sources.microsoft_graph.sync_calendars") as sc:
                with patch("bunker.continuity.sources.microsoft_graph.sync_contacts") as sct:
                    with patch(
                        "bunker.continuity.sources.microsoft_graph.sync_sharepoint_folder",
                        side_effect=RuntimeError("sp down"),
                    ):
                        sc.return_value = {"ok": True}
                        sct.return_value = {"ok": True}
                        with patch("bunker.continuity.sync_all.generate_outage_pack_pdf"):
                            out = run_continuity_sync(paths, cfg)
    assert len(out) == 1


def test_merge_hints_from_config() -> None:
    hints = _merge_hints_from_config(
        Path("."),
        [{"id": "a", "primary_key": "id", "parquet_partition": "ingest_date"}],
    )
    assert hints[0]["source_id"] == "a"


def test_doctor_full_run_missing_continuity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "p"
    root.mkdir()
    (root / "config").mkdir()
    (root / "config" / "sources.yaml").write_text(
        "bunker:\n  data_root: data\nsources: []\n", encoding="utf-8"
    )
    monkeypatch.chdir(root)
    names = {r.name for r in run_doctor()}
    assert "continuity.yaml" in names


def test_run_watch_live_probes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from bunker.continuity.watch.health import WatchConfig, run_watch

    class Resp:
        status_code = 200

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def get(self, url):
            return Resp()

    monkeypatch.setattr(httpx, "Client", lambda **k: Client())
    cfg = WatchConfig(
        probe_hosts=[{"name": "outlook", "url": "https://example.com"}],
    )
    state = run_watch(cfg, tmp_path / "w.json")
    assert state.probes is not None


def test_run_watch_with_graph_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from bunker.continuity.graph.auth import StaticTokenProvider
    from bunker.continuity.graph.client import HttpxGraphClient
    from bunker.continuity.watch.health import WatchConfig, run_watch

    client = HttpxGraphClient(StaticTokenProvider("tok"))

    def fake_get(path: str, **kwargs):
        if "healthOverviews" in path:
            return {"value": []}
        return {"value": []}

    monkeypatch.setattr(client, "get", fake_get)
    cfg = WatchConfig(
        probe_hosts=[],
        auth_probe_path="/me/messages?$top=1",
    )
    run_watch(cfg, tmp_path / "w2.json", graph_client=client)


def test_probe_graph_health_unreachable() -> None:
    from bunker.continuity.watch.health import probe_graph_health

    class BadClient:
        def get(self, path: str):
            raise RuntimeError("graph down")

    ok, bad, names = probe_graph_health(BadClient(), watched_services=["Teams"])  # type: ignore[arg-type]
    assert ok is False


def test_sync_all_encryption_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import continuity_paths

    from bunker.continuity.encryption import EncryptionRequiredError

    paths = continuity_paths(tmp_path)
    cfg = {"continuity": {"require_encryption": True}}
    monkeypatch.delenv("BUNKER_DATA_KEY", raising=False)
    with pytest.raises(EncryptionRequiredError):
        run_continuity_sync(paths, cfg)


def test_build_token_provider_static(monkeypatch: pytest.MonkeyPatch) -> None:
    from bunker.continuity.graph.auth import StaticTokenProvider, build_token_provider

    monkeypatch.setenv("BUNKER_GRAPH_ACCESS_TOKEN", "abc123")
    prov = build_token_provider()
    assert isinstance(prov, StaticTokenProvider)
    assert prov.get_token() == "abc123"
    prov.invalidate_token()


def test_graph_auth_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from bunker.continuity.graph.auth import GraphAuthSettings

    monkeypatch.setenv("BUNKER_GRAPH_TENANT_ID", "t")
    monkeypatch.setenv("BUNKER_GRAPH_CLIENT_ID", "c")
    s = GraphAuthSettings.from_env()
    assert s is not None
    assert s.tenant_id == "t"


def test_signing_key_perms_ok(project_tree: Path) -> None:
    pytest.importorskip("posix")
    paths = BunkerPaths.from_config(
        project_tree,
        {"bunker": {"data_root": "data", "cache_root": "cache", "sync_root": "."}},
    )
    priv = paths.data_root / "keys" / "signing.pem"
    priv.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert _check_signing_key(paths).passed