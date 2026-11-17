from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from bunker.ingest.dedup import compact_partition
from bunker.paths import BunkerPaths
from bunker.sync.partition_paths import select_shards_for_hint, validate_relative_partition
from bunker.sync.verify import verify_sync_folder

logger = logging.getLogger(__name__)


def import_sync_bundle(
    sync_dir: Path,
    paths: BunkerPaths,
    *,
    public_key: Ed25519PublicKey,
) -> dict[str, str | int]:
    ok, errors = verify_sync_folder(sync_dir, public_key=public_key, require_signature=True)
    if not ok:
        raise ValueError("Bundle verification failed: " + "; ".join(errors))

    manifest = json.loads((sync_dir / "manifest.json").read_text(encoding="utf-8"))
    shards_src = sync_dir / "shards"
    if not shards_src.is_dir():
        raise ValueError("Bundle has no shards/ directory")

    shard_files = sorted(shards_src.glob("*.parquet"))
    copied = 0
    archive_root = paths.parquet_root / "imported" / sync_dir.name / "ingest_date=import"
    archive_root.mkdir(parents=True, exist_ok=True)
    for shard in shard_files:
        shutil.copy2(shard, archive_root / f"part-{shard.name}")
        copied += 1

    parquet_resolved = paths.parquet_root.resolve()
    currents: list[str] = []
    for hint in manifest.get("merge_hints") or []:
        pk = hint.get("primary_key")
        partition = hint.get("target_partition")
        if not pk or not partition:
            continue
        rel_part = validate_relative_partition(str(partition))
        part_root = paths.parquet_root / rel_part
        if not part_root.resolve().is_relative_to(parquet_resolved):
            raise ValueError(f"target_partition escapes data root: {partition!r}")
        matching = select_shards_for_hint(shard_files, hint)
        if not matching:
            logger.warning(
                "No bundle shards matched target_partition %r (source_id=%s)",
                partition,
                hint.get("source_id"),
            )
            continue
        ingest_root = part_root / "ingest_date=import"
        ingest_root.mkdir(parents=True, exist_ok=True)
        for shard in matching:
            shutil.copy2(shard, ingest_root / f"part-{shard.name}")
        cur = compact_partition(part_root, str(pk))
        if cur:
            currents.append(str(cur))

    return {
        "imported_shards": copied,
        "archive": str(archive_root.parent),
        "merged_current": ",".join(currents),
    }