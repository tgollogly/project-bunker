from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from bunker import __version__
from bunker.cli import main
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.schedule.install import ScheduleSpec, plan_schedule
from bunker.continuity.seed_sample import seed_sample_data
from bunker.continuity.serve.view_context import runbook_plaintext
from bunker.continuity.sources.registry import run_configured_sources
from bunker.crypto.signing import load_private_key, load_public_key
from bunker.ingest.parquet_writer import write_rows_parquet_duckdb
from bunker.paths import BunkerPaths
from bunker.sync.import_bundle import import_sync_bundle
from bunker.sync.manifest import ManifestBuilder
from bunker.sync.partition_paths import select_shards_for_hint, validate_relative_partition
from bunker.sync.schema_doc import build_schema_json


def test_package_version_matches_pyproject() -> None:
    assert __version__ == "0.4.2"


def test_cli_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.4.2" in result.output


def test_seed_sample_without_preconfigured_key(
    project_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project_tree / "config" / "continuity.yaml").write_text(
        "continuity:\n  data_root: data/continuity\n  require_encryption: true\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_tree)
    paths = ContinuityPaths.from_config(
        project_tree, {"continuity": {"data_root": "data/continuity"}}
    )
    seed_sample_data(paths)


def test_schedule_install_dry_run() -> None:
    out = plan_schedule(ScheduleSpec(interval_hours=3))
    assert out["dry_run"] == "true"
    assert out["interval_hours"] == "3"


def test_runbook_path_traversal_blocked(tmp_path: Path, bunker_data_key: str) -> None:
    paths = ContinuityPaths.from_config(tmp_path, {"continuity": {"data_root": "data/continuity"}})
    paths.ensure()
    with pytest.raises(ValueError):
        runbook_plaintext(paths, "../outside.md")


def test_validate_partition_rejects_traversal() -> None:
    with pytest.raises(ValueError):
        validate_relative_partition("../evil")
    with pytest.raises(ValueError):
        validate_relative_partition("demo/../../x")


def test_import_merge_two_partitions(tmp_path: Path, signing_keys) -> None:
    root = tmp_path
    priv, pub = signing_keys
    key_dir = root / "data" / "keys"
    key_dir.mkdir(parents=True)
    key_dir.joinpath("signing.pem").write_bytes(priv.read_bytes())
    key_dir.joinpath("signing.pub.pem").write_bytes(pub.read_bytes())

    cfg = {"bunker": {"data_root": "data", "cache_root": "cache", "sync_root": "."}}
    paths = BunkerPaths.from_config(root, cfg)
    paths.ensure()

    bundle = root / "bunker_sync_multi"
    shards = bundle / "shards"
    shards.mkdir(parents=True)
    shard_a = shards / "alpha.parquet"
    shard_b = shards / "beta.parquet"
    write_rows_parquet_duckdb([{"k": "a", "v": 1, "_bunker_ingested_at": "t1"}], shard_a)
    write_rows_parquet_duckdb([{"k": "b", "v": 2, "_bunker_ingested_at": "t2"}], shard_b)

    alpha_root = paths.parquet_root / "alpha"
    beta_root = paths.parquet_root / "beta"
    alpha_root.mkdir(parents=True)
    beta_root.mkdir(parents=True)

    ManifestBuilder(bundle).build(
        [shard_a, shard_b],
        private_key=load_private_key(priv),
        merge_hints=[
            {"target_partition": "alpha", "primary_key": "k", "source_id": "alpha"},
            {"target_partition": "beta", "primary_key": "k", "source_id": "beta"},
        ],
    )

    import_sync_bundle(bundle, paths, public_key=load_public_key(pub))
    assert (alpha_root / "_current.parquet").is_file()
    assert (beta_root / "_current.parquet").is_file()


def test_registry_continues_after_source_failure(
    tmp_path: Path, bunker_data_key: str
) -> None:
    from conftest import continuity_paths

    paths = continuity_paths(tmp_path)

    class OkSource:
        id = "ok"

        def sync(self, paths: ContinuityPaths, cfg: dict) -> dict:
            return {"source_id": self.id, "row_count": 1}

    class BadSource:
        id = "bad"

        def sync(self, paths: ContinuityPaths, cfg: dict) -> dict:
            raise RuntimeError("simulated failure")

    cfg = {
        "continuity": {
            "sync_sources": [
                {"id": "ok", "type": "microsoft_graph", "enabled": True},
                {"id": "bad", "type": "microsoft_graph", "enabled": True},
            ]
        }
    }

    with patch(
        "bunker.continuity.sources.registry._build_source",
        side_effect=[OkSource(), BadSource()],
    ):
        results = run_configured_sources(paths, cfg)
    assert len(results) == 2
    assert results[0]["ok"] is True
    assert results[1]["ok"] is False


def test_build_schema_json_plain_parquet(tmp_path: Path) -> None:
    pf = tmp_path / "demo.parquet"
    write_rows_parquet_duckdb([{"x": 1}], pf)
    out = tmp_path / "schema.json"
    doc = build_schema_json([pf], out)
    assert doc["datasets"]
    assert out.is_file()


def test_select_shards_fallback_source_id() -> None:
    shards = [Path("usgs__day.parquet")]
    hint = {"target_partition": "usgs/earthquakes/day", "source_id": "usgs"}
    picked = select_shards_for_hint(shards, hint)
    assert picked == shards


def test_import_rejects_bad_partition(tmp_path: Path, signing_keys) -> None:
    root = tmp_path
    priv, pub = signing_keys
    key_dir = root / "data" / "keys"
    key_dir.mkdir(parents=True)
    key_dir.joinpath("signing.pem").write_bytes(priv.read_bytes())
    key_dir.joinpath("signing.pub.pem").write_bytes(pub.read_bytes())
    cfg = {"bunker": {"data_root": "data", "cache_root": "cache", "sync_root": "."}}
    paths = BunkerPaths.from_config(root, cfg)
    bundle = root / "bunker_sync_bad"
    shards = bundle / "shards"
    shards.mkdir(parents=True)
    shard = shards / "x.parquet"
    write_rows_parquet_duckdb([{"k": "1"}], shard)
    ManifestBuilder(bundle).build(
        [shard],
        private_key=load_private_key(priv),
        merge_hints=[{"target_partition": "../escape", "primary_key": "k"}],
    )
    with pytest.raises(ValueError):
        import_sync_bundle(bundle, paths, public_key=load_public_key(pub))


def test_query_blocks_writes() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["query", "DROP TABLE x"])
    assert result.exit_code != 0