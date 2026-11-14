import json
from pathlib import Path

from bunker.crypto.signing import load_public_key
from bunker.ingest.parquet_writer import write_rows_parquet_duckdb
from bunker.keys import keygen
from bunker.paths import BunkerPaths
from bunker.sync.import_bundle import import_sync_bundle
from bunker.sync.package import package_airgap_sync
from bunker.sync.verify import verify_sync_folder


def test_airgap_package_import_verify(tmp_path: Path) -> None:
    root = tmp_path
    keygen(root)
    cfg = {"bunker": {"data_root": "data", "cache_root": "cache", "sync_root": "."}}
    paths = BunkerPaths.from_config(root, cfg)
    paths.ensure()
    part_dir = paths.parquet_root / "demo" / "ingest_date=2099-01-01"
    part_dir.mkdir(parents=True)
    part = part_dir / "part-test.parquet"
    write_rows_parquet_duckdb([{"id": 1, "name": "bunker", "_bunker_ingested_at": "t"}], part)

    sync_dir = package_airgap_sync(paths)
    pub = load_public_key(root / "data" / "keys" / "signing.pub.pem")
    ok, errs = verify_sync_folder(sync_dir, public_key=pub, require_signature=True)
    assert ok, errs
    schema = json.loads((sync_dir / "schema.json").read_text())
    assert schema["datasets"]

    result = import_sync_bundle(
        sync_dir,
        paths,
        public_key=pub,
    )
    assert result["imported_shards"] >= 1