import pytest

from bunker.ingest.parquet_writer import write_rows_parquet_duckdb
from bunker.paths import BunkerPaths
from bunker.sync.package import package_airgap_sync


def test_package_raises_without_signing_key(tmp_path) -> None:
    cfg = {"bunker": {"data_root": "data", "cache_root": "cache", "sync_root": "."}}
    paths = BunkerPaths.from_config(tmp_path, cfg)
    paths.ensure()
    part = paths.parquet_root / "x" / "ingest_date=2026-11-14" / "part-0.parquet"
    part.parent.mkdir(parents=True)
    write_rows_parquet_duckdb([{"id": 1, "_bunker_ingested_at": "t"}], part)
    with pytest.raises(FileNotFoundError, match="keygen"):
        package_airgap_sync(paths)


def test_package_raises_when_empty(tmp_path, signing_keys) -> None:
    cfg = {"bunker": {"data_root": "data", "cache_root": "cache", "sync_root": "."}}
    paths = BunkerPaths.from_config(tmp_path, cfg)
    paths.ensure()
    priv, pub = signing_keys
    key_dir = paths.data_root / "keys"
    key_dir.mkdir(parents=True)
    key_dir.joinpath("signing.pem").write_bytes(priv.read_bytes())
    key_dir.joinpath("signing.pub.pem").write_bytes(pub.read_bytes())
    with pytest.raises(ValueError, match="Nothing to package"):
        package_airgap_sync(paths)