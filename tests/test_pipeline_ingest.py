from pathlib import Path

from bunker.ingest.pipeline import ingest_source
from bunker.paths import BunkerPaths

USGS_SAMPLE = b"""{
  "features": [{
    "id": "evt1",
    "properties": {"mag": 2.1, "place": "Test"},
    "geometry": {"coordinates": [0, 0, 1]}
  }]
}"""


def test_offline_ingest_and_dedup_across_runs(tmp_path: Path) -> None:
    root = tmp_path
    cfg = {"bunker": {"data_root": "data", "cache_root": "cache", "sync_root": "."}}
    paths = BunkerPaths.from_config(root, cfg)
    paths.ensure()
    cache = paths.cache_root
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "usgs_earthquakes_day.bin").write_bytes(USGS_SAMPLE)
    (cache / "usgs_earthquakes_day.meta.json").write_text(
        '{"fetched_at": 1, "content_type": "application/json"}'
    )

    source = {
        "id": "usgs_earthquakes_day",
        "url": "https://example.invalid",
        "parser": "usgs_earthquakes_day",
        "primary_key": "_feature_id",
        "parquet_partition": "usgs/earthquakes/day",
    }

    r1 = ingest_source(paths, source, force_cache_only=True)
    r2 = ingest_source(paths, source, force_cache_only=True)
    assert r1["row_count"] == 1
    assert r2["row_count"] == 1
    current = paths.parquet_root / "usgs/earthquakes/day/_current.parquet"
    assert current.is_file()