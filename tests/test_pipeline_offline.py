import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from bunker.paths import BunkerPaths
from bunker.sync.package import package_airgap_sync
from bunker.sync.verify import verify_sync_folder


def test_airgap_package_and_verify(tmp_path: Path) -> None:
    root = tmp_path
    cfg = {"bunker": {"data_root": "data", "cache_root": "cache", "sync_root": "."}}
    paths = BunkerPaths.from_config(root, cfg)
    paths.ensure()
    out = paths.parquet_root / "demo" / "data.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist([{"id": 1, "name": "bunker"}])
    pq.write_table(table, out, compression="zstd")

    sync_dir = package_airgap_sync(paths)
    assert sync_dir.is_dir()
    assert (sync_dir / "manifest.json").is_file()
    assert (sync_dir / "schema.json").is_file()
    ok, errs = verify_sync_folder(sync_dir)
    assert ok, errs
    schema = json.loads((sync_dir / "schema.json").read_text())
    assert schema["datasets"]