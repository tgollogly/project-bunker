"""Validate parquet partition paths and match bundle shards to merge hints."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_PARTITION_SEGMENT = re.compile(r"^[A-Za-z0-9_.=-]+$")


def validate_relative_partition(partition: str) -> str:
    """Reject path traversal and unsafe segments for paths under parquet_root."""
    rel = partition.strip().strip("/\\")
    if not rel:
        raise ValueError(f"invalid target_partition: {partition!r}")
    for seg in rel.replace("\\", "/").split("/"):
        if not seg or seg in (".", "..") or not _PARTITION_SEGMENT.fullmatch(seg):
            raise ValueError(f"invalid target_partition: {partition!r}")
    return rel


def partition_rel_to_shard_prefix(partition: str) -> str:
    return validate_relative_partition(partition).replace("/", "__")


def select_shards_for_hint(shard_files: list[Path], hint: dict[str, Any]) -> list[Path]:
    """Map merge_hints entry to Parquet shards packaged with matching names."""
    partition = hint.get("target_partition")
    if not partition:
        return []
    prefix = partition_rel_to_shard_prefix(str(partition))
    matched = [
        s
        for s in shard_files
        if s.name == f"{prefix}.parquet" or s.name.startswith(f"{prefix}__")
    ]
    if matched:
        return matched
    source_id = hint.get("source_id")
    if source_id:
        sid = re.sub(r"[^A-Za-z0-9_.=-]", "_", str(source_id))
        matched = [s for s in shard_files if s.name.startswith(f"{sid}__")]
        if matched:
            return matched
    if len(shard_files) == 1:
        return list(shard_files)
    return []