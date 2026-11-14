from __future__ import annotations

import logging
import shutil
from datetime import date
from pathlib import Path

from bunker.config import load_sources_config
from bunker.continuity.parquet_io import ENCRYPTED_PARQUET_SUFFIX
from bunker.continuity.paths import ContinuityPaths
from bunker.crypto.signing import load_private_key
from bunker.paths import BunkerPaths
from bunker.sync.manifest import ManifestBuilder
from bunker.sync.schema_doc import build_schema_json

logger = logging.getLogger(__name__)


def collect_parquet_files(parquet_root: Path, extra_roots: list[Path] | None = None) -> list[Path]:
    files: list[Path] = []
    roots = [parquet_root, *(extra_roots or [])]
    for root in roots:
        if not root.is_dir():
            continue
        for pattern in (
            "**/_current.parquet",
            "**/ingest_date=*/part-*.parquet",
            f"**/*{ENCRYPTED_PARQUET_SUFFIX}",
        ):
            files.extend(sorted(root.glob(pattern)))
    return sorted(set(files))


def _merge_hints_from_config(root: Path, sources: list[dict]) -> list[dict]:
    hints: list[dict] = []
    for src in sources:
        pk = src.get("primary_key")
        part = src.get("parquet_partition")
        if pk and part:
            hints.append(
                {
                    "source_id": src["id"],
                    "target_partition": part,
                    "primary_key": pk,
                }
            )
    _ = root  # reserved for future config paths
    return hints


def package_airgap_sync(
    paths: BunkerPaths,
    *,
    on: date | None = None,
    include_readme: bool = True,
    private_key_path: Path | None = None,
) -> Path:
    """
    Create bunker_sync_YYYY-MM-DD/ with Parquet shards, schema.json, signed manifest.json.
    """
    sync_dir = paths.sync_folder(on)
    shards = sync_dir / "shards"
    if sync_dir.exists():
        shutil.rmtree(sync_dir)
    shards.mkdir(parents=True)

    extra: list[Path] = []
    continuity_cfg_path = paths.root / "config" / "continuity.yaml"
    if continuity_cfg_path.is_file():
        from bunker.continuity.config import load_continuity_config

        cpaths = ContinuityPaths.from_config(
            paths.root, load_continuity_config(continuity_cfg_path)
        )
        extra.append(cpaths.parquet_root)
    sources = collect_parquet_files(paths.parquet_root, extra_roots=extra)
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
                    "Query in DuckDB:",
                    "  SELECT * FROM read_parquet('shards/*.parquet', union_by_name=true);",
                    "",
                    "Verify:",
                    "  bunker verify-sync <bundle> --public-key data/keys/signing.pub.pem",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        manifest_targets.append(readme)

    key_path = private_key_path or (paths.root / "data" / "keys" / "signing.pem")
    if not key_path.is_file():
        raise FileNotFoundError(
            f"Signing key not found at {key_path}. Run: bunker keygen"
        )
    private_key = load_private_key(key_path)

    cfg_path = paths.root / "config" / "sources.yaml"
    merge_hints: list[dict] = []
    if cfg_path.is_file():
        cfg = load_sources_config(cfg_path)
        merge_hints = _merge_hints_from_config(paths.root, cfg.get("sources", []))

    ManifestBuilder(sync_dir).build(
        manifest_targets,
        private_key=private_key,
        merge_hints=merge_hints or None,
    )
    logger.info("Packaged signed air-gap sync at %s", sync_dir)
    return sync_dir