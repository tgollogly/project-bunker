from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from bunker.ingest.fetcher import ResilientFetcher
from bunker.paths import BunkerPaths

logger = logging.getLogger(__name__)


def _save_raw(paths: BunkerPaths, source_id: str, payload: bytes) -> Path:
    dest = paths.raw_root / source_id
    dest.mkdir(parents=True, exist_ok=True)
    stamp = Path("latest.bin")
    out = dest / stamp
    out.write_bytes(payload)
    return out


def _geojson_features_to_rows(payload: bytes) -> list[dict[str, Any]]:
    doc = json.loads(payload)
    features = doc.get("features") or []
    rows: list[dict[str, Any]] = []
    for feat in features:
        props = dict(feat.get("properties") or {})
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or [None, None, None]
        props["_lon"] = coords[0] if len(coords) > 0 else None
        props["_lat"] = coords[1] if len(coords) > 1 else None
        props["_depth_km"] = coords[2] if len(coords) > 2 else None
        props["_feature_id"] = feat.get("id")
        rows.append(props)
    return rows


def _open_meteo_to_rows(payload: bytes) -> list[dict[str, Any]]:
    doc = json.loads(payload)
    hourly = doc.get("hourly") or {}
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    rows: list[dict[str, Any]] = []
    for i, t in enumerate(times):
        rows.append(
            {
                "time": t,
                "temperature_2m": temps[i] if i < len(temps) else None,
                "latitude": doc.get("latitude"),
                "longitude": doc.get("longitude"),
            }
        )
    return rows


def _write_parquet(rows: list[dict[str, Any]], out_file: Path) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, out_file, compression="zstd")


def ingest_source(
    paths: BunkerPaths,
    source: dict[str, Any],
    *,
    force_cache_only: bool = False,
) -> dict[str, Any]:
    """Ingest one configured source into partitioned Parquet via DuckDB."""
    paths.ensure()
    source_id = source["id"]
    cache_key = source_id
    fetcher = ResilientFetcher(paths.cache_root)

    if force_cache_only:
        result = fetcher._read_cache(cache_key)
        if result is None:
            raise RuntimeError(f"No cache for {source_id}; cannot run offline-only ingest")
    else:
        result = fetcher.fetch(
            source["url"],
            cache_key,
            min_interval_seconds=float(source.get("min_fetch_interval_seconds", 0)),
        )

    raw_path = _save_raw(paths, source_id, result.payload)
    fmt = source.get("format", "json")

    if fmt == "geojson":
        rows = _geojson_features_to_rows(result.payload)
    elif fmt == "json":
        rows = _open_meteo_to_rows(result.payload)
    else:
        raise ValueError(f"Unsupported format: {fmt}")

    partition = source.get("parquet_partition", source_id)
    out_file = paths.parquet_root / partition / "data.parquet"
    if rows:
        _write_parquet(rows, out_file)
    else:
        logger.warning("Source %s returned zero rows", source_id)

    return {
        "source_id": source_id,
        "from_cache": result.from_cache,
        "raw_path": str(raw_path),
        "parquet_path": str(out_file),
        "row_count": len(rows),
        "attribution": source.get("attribution"),
    }