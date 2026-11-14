from bunker.crypto.signing import load_private_key, load_public_key
from bunker.ingest.parquet_writer import write_rows_parquet_duckdb
from bunker.paths import BunkerPaths
from bunker.sync.import_bundle import import_sync_bundle
from bunker.sync.manifest import ManifestBuilder


def test_import_applies_merge_hints(tmp_path, signing_keys) -> None:
    root = tmp_path
    priv, pub = signing_keys
    key_dir = root / "data" / "keys"
    key_dir.mkdir(parents=True)
    key_dir.joinpath("signing.pem").write_bytes(priv.read_bytes())
    key_dir.joinpath("signing.pub.pem").write_bytes(pub.read_bytes())

    cfg = {"bunker": {"data_root": "data", "cache_root": "cache", "sync_root": "."}}
    paths = BunkerPaths.from_config(root, cfg)
    paths.ensure()
    part_root = paths.parquet_root / "demo"
    part = part_root / "ingest_date=2099-01-01" / "part-a.parquet"
    write_rows_parquet_duckdb([{"k": "1", "v": 1, "_bunker_ingested_at": "t1"}], part)

    bundle = root / "bunker_sync_test"
    shards = bundle / "shards"
    shards.mkdir(parents=True)
    shard = shards / "demo.parquet"
    write_rows_parquet_duckdb([{"k": "2", "v": 9, "_bunker_ingested_at": "t2"}], shard)
    ManifestBuilder(bundle).build(
        [shard],
        private_key=load_private_key(priv),
        merge_hints=[{"target_partition": "demo", "primary_key": "k"}],
    )

    result = import_sync_bundle(bundle, paths, public_key=load_public_key(pub))
    assert result["imported_shards"] == 1
    current = part_root / "_current.parquet"
    assert current.is_file()