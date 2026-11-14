from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bunker.ingest.dedup import compact_partition
from bunker.ingest.fetcher import ResilientFetcher
from bunker.ingest.parquet_writer import hive_part_path, write_rows_parquet_duckdb
from bunker.ingest.parsers import resolve_parser
from bunker.io.atomic import atomic_write_bytes
from bunker.paths import BunkerPaths

logger = logging.getLogger(__name__)


def _save_raw(paths: BunkerPaths, source_id: str, payload: bytes) -> Path:
    dest = paths.raw_root / source_id
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / "latest.bin"
    atomic_write_bytes(out, payload)
    return out


def ingest_source(
    paths: BunkerPaths,
    source: dict[str, Any],
    *,
    force_cache_only: bool = False,
) -> dict[str, Any]:
    """Ingest one configured source into hive-partitioned Parquet via DuckDB."""
    paths.ensure()
    source_id = source["id"]
    cache_key = source_id
    fetcher = ResilientFetcher(paths.cache_root)

    if force_cache_only:
        result = fetcher._read_cache(cache_key, reason="fallback")
        if result is None:
            raise RuntimeError(f"No cache for {source_id}; cannot run offline-only ingest")
    else:
        result = fetcher.fetch(
            source["url"],
            cache_key,
            min_interval_seconds=float(source.get("min_fetch_interval_seconds", 0)),
        )

    raw_path = _save_raw(paths, source_id, result.payload)
    parser = resolve_parser(source)
    rows = parser(result.payload)
    ingested_at = datetime.now(timezone.utc).isoformat()
    for row in rows:
        row["_bunker_ingested_at"] = ingested_at

    partition = source.get("parquet_partition", source_id)
    partition_root = paths.parquet_root / partition
    part_path = hive_part_path(partition_root)
    current_path: Path | None = None

    if rows:
        write_rows_parquet_duckdb(rows, part_path)
        primary_key = source.get("primary_key")
        if primary_key:
            current_path = compact_partition(partition_root, primary_key)
    else:
        logger.warning("Source %s returned zero rows", source_id)
        part_path = partition_root  # unused sentinel for empty

    return {
        "source_id": source_id,
        "from_cache": result.from_cache,
        "cache_reason": result.cache_reason,
        "raw_path": str(raw_path),
        "parquet_part": str(part_path) if rows else None,
        "parquet_current": str(current_path) if current_path else None,
        "row_count": len(rows),
        "attribution": source.get("attribution"),
    }