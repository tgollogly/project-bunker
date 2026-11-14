from __future__ import annotations

import logging
import shutil
from datetime import date
from pathlib import Path

from bunker.paths import BunkerPaths
from bunker.sync.manifest import ManifestBuilder
from bunker.sync.schema_doc import build_schema_json

logger = logging.getLogger(__name__)


def collect_parquet_files(parquet_root: Path) -> list[Path]:
    if not parquet_root.is_dir():
        return []
    return sorted(parquet_root.rglob("*.parquet"))


def package_airgap_sync(
    paths: BunkerPaths,
    *,
    on: date | None = None,
    include_readme: bool = True,
) -> Path:
    """
    Create bunker_sync_YYYY-MM-DD/ with Parquet shards, schema.json, manifest.json.
    Suitable for LAN copy, USB handoff, or P2P folder sync — queryable by DuckDB offline.
    """
    sync_dir = paths.sync_folder(on)
    shards = sync_dir / "shards"
    if sync_dir.exists():
        shutil.rmtree(sync_dir)
    shards.mkdir(parents=True)

    sources = collect_parquet_files(paths.parquet_root)
    copied: list[Path] = []
    for src in sources:
        dest = shards / src.relative_to(paths.parquet_root).as_posix().replace("/", "__")
        shutil.copy2(src, dest)
        copied.append(dest)

    if not copied:
        logger.warning("No Parquet files found under %s", paths.parquet_root)

    schema_path = sync_dir / "schema.json"
    build_schema_json(copied, schema_path)

    manifest_targets: list[Path] = [schema_path, *copied]
    if include_readme:
        readme = sync_dir / "OFFLINE_README.txt"
        readme.write_text(
            "\n".join(
                [
                    "Project Bunker — Air-Gapped Sync Bundle",
                    "Copyright © 2026 Thomas Gollogly. All rights reserved.",
                    "",
                    "Query in DuckDB (no imports required):",
                    "  SELECT * FROM read_parquet('shards/*.parquet');",
                    "",
                    "Verify integrity:",
                    "  bunker verify-sync .",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        manifest_targets.append(readme)

    ManifestBuilder(sync_dir).build(manifest_targets)
    logger.info("Packaged air-gap sync at %s", sync_dir)
    return sync_dir