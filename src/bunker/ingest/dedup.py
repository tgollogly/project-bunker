from __future__ import annotations

from pathlib import Path

import duckdb

from bunker.io.atomic import atomic_write_bytes
from bunker.sql_ident import validate_sql_identifier


def compact_partition(partition_root: Path, primary_key: str) -> Path | None:
    """
    Collapse all hive parts under partition_root into _current.parquet,
  keeping the latest row per primary_key by _bunker_ingested_at.
    """
    glob = str(partition_root / "ingest_date=*" / "part-*.parquet")
    con = duckdb.connect(database=":memory:")
    try:
        row = con.execute(
            "SELECT COUNT(*) FROM read_parquet(?, union_by_name=true)",
            [glob],
        ).fetchone()
        if row is None:
            return None
        n = row[0]
        if n == 0:
            return None
        pk = validate_sql_identifier(primary_key, label="primary key")
        out = partition_root / "_current.parquet"
        tmp = partition_root / "._current.parquet.tmp"
        dedup_sql = (
            "COPY ("
            " SELECT * EXCLUDE (rn) FROM ("
            " SELECT *, row_number() OVER ("
            " PARTITION BY "
            + pk
            + " ORDER BY _bunker_ingested_at DESC) AS rn"
            " FROM read_parquet(?, union_by_name=true)"
            " ) WHERE rn = 1"
            ") TO ? (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        con.execute(dedup_sql, [glob, str(tmp)])
        atomic_write_bytes(out, tmp.read_bytes())
        tmp.unlink(missing_ok=True)
        return out
    finally:
        con.close()