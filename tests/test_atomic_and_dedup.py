from datetime import date
from pathlib import Path

import pyarrow.parquet as pq

from bunker.ingest.dedup import compact_partition
from bunker.ingest.parquet_writer import hive_part_path, write_rows_parquet_duckdb
from bunker.io.atomic import atomic_write_bytes


def test_atomic_write_replaces_dest(tmp_path: Path) -> None:
    f = tmp_path / "x.bin"
    f.write_bytes(b"old")
    atomic_write_bytes(f, b"new")
    assert f.read_bytes() == b"new"


def test_dedup_keeps_latest_ingest(tmp_path: Path) -> None:
    root = tmp_path / "usgs"
    d = date.today()
    part1 = root / f"ingest_date={d.isoformat()}" / "part-1.parquet"
    part2 = root / f"ingest_date={d.isoformat()}" / "part-2.parquet"
    write_rows_parquet_duckdb(
        [{"_feature_id": "a", "mag": 1.0, "_bunker_ingested_at": "t1"}],
        part1,
    )
    write_rows_parquet_duckdb(
        [{"_feature_id": "a", "mag": 9.0, "_bunker_ingested_at": "t2"}],
        part2,
    )
    current = compact_partition(root, "_feature_id")
    assert current is not None
    t = pq.read_table(current)
    assert t.column("mag")[0].as_py() == 9.0


def test_hive_part_path_layout(tmp_path: Path) -> None:
    p = hive_part_path(tmp_path / "lake", date(2026, 1, 2))
    assert "ingest_date=2026-01-02" in p.as_posix()
    assert p.name.startswith("part-")