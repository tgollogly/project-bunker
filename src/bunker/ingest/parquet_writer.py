from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa

from bunker.io.atomic import atomic_write_bytes


def hive_part_path(partition_root: Path, ingest_date: date | None = None) -> Path:
    d = ingest_date or date.today()
    part_dir = partition_root / f"ingest_date={d.isoformat()}"
    part_dir.mkdir(parents=True, exist_ok=True)
    return part_dir / f"part-{uuid.uuid4().hex}.parquet"


def write_rows_parquet_duckdb(rows: list[dict[str, Any]], dest: Path) -> Path:
    """Write Parquet via DuckDB COPY (zstd). Uses atomic replace on completion."""
    if not rows:
        raise ValueError("write_rows_parquet_duckdb requires at least one row")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".parquet.tmp")
    con = duckdb.connect(database=":memory:")
    try:
        con.register("ingest_rows", pa.Table.from_pylist(rows))
        con.execute(
            "COPY ingest_rows TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(tmp)],
        )
        data = tmp.read_bytes()
        atomic_write_bytes(dest, data)
    finally:
        con.close()
        tmp.unlink(missing_ok=True)
    return dest