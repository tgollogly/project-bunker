from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from bunker.config import get_source, load_sources_config
from bunker.duckdb_engine import BunkerDuckDB
from bunker.ingest.pipeline import ingest_source
from bunker.paths import BunkerPaths
from bunker.sync.package import package_airgap_sync
from bunker.sync.verify import verify_sync_folder

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("bunker")


def _project_root() -> Path:
    return Path.cwd()


@click.group()
@click.option("--config", "config_path", type=click.Path(path_type=Path), default="config/sources.yaml")
@click.pass_context
def main(ctx: click.Context, config_path: Path) -> None:
    """Project Bunker — offline-first DuckDB data engine."""
    root = _project_root()
    cfg = load_sources_config(root / config_path if not config_path.is_absolute() else config_path)
    paths = BunkerPaths.from_config(root, cfg)
    ctx.ensure_object(dict)
    ctx.obj["cfg"] = cfg
    ctx.obj["paths"] = paths


@main.command("ingest")
@click.option("--source", "source_id", required=True, help="Source id from config/sources.yaml")
@click.option("--offline", is_flag=True, help="Use cache only (air-gapped / blackout mode)")
@click.pass_context
def cmd_ingest(ctx: click.Context, source_id: str, offline: bool) -> None:
    paths: BunkerPaths = ctx.obj["paths"]
    cfg = ctx.obj["cfg"]
    source = get_source(cfg, source_id)
    result = ingest_source(paths, source, force_cache_only=offline)
    click.echo(json.dumps(result, indent=2))


@main.command("ingest-all")
@click.option("--offline", is_flag=True)
@click.pass_context
def cmd_ingest_all(ctx: click.Context, offline: bool) -> None:
    paths: BunkerPaths = ctx.obj["paths"]
    cfg = ctx.obj["cfg"]
    results = []
    for source in cfg.get("sources", []):
        try:
            results.append(ingest_source(paths, source, force_cache_only=offline))
        except Exception as exc:
            logger.error("Ingest failed for %s: %s", source.get("id"), exc)
    click.echo(json.dumps(results, indent=2))


@main.command("sync-package")
@click.pass_context
def cmd_sync_package(ctx: click.Context) -> None:
    paths: BunkerPaths = ctx.obj["paths"]
    out = package_airgap_sync(paths)
    click.echo(str(out))


@main.command("verify-sync")
@click.argument("sync_dir", type=click.Path(path_type=Path, exists=True))
def cmd_verify_sync(sync_dir: Path) -> None:
    ok, errors = verify_sync_folder(sync_dir)
    if ok:
        click.echo("OK — manifest verification passed")
        sys.exit(0)
    for e in errors:
        click.echo(f"ERROR: {e}", err=True)
    sys.exit(1)


@main.command("query")
@click.argument("sql")
@click.pass_context
def cmd_query(ctx: click.Context, sql: str) -> None:
    paths: BunkerPaths = ctx.obj["paths"]
    pattern = str(paths.parquet_root / "**" / "*.parquet")
    with BunkerDuckDB() as db:
        db.register_parquet_glob("bunker_data", pattern)
        rel = db.query(sql.replace("bunker_data", "bunker_data"))
        rows = rel.fetchall()
        cols = [d[0] for d in rel.description] if rel.description else []
        if not rows:
            click.echo("(no rows)")
            return
        widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) for i, c in enumerate(cols)]
        click.echo("  ".join(c.ljust(widths[i]) for i, c in enumerate(cols)))
        for r in rows:
            click.echo("  ".join(str(r[i]).ljust(widths[i]) for i in range(len(cols))))


@main.command("status")
@click.pass_context
def cmd_status(ctx: click.Context) -> None:
    paths: BunkerPaths = ctx.obj["paths"]
    pattern = str(paths.parquet_root / "**" / "*.parquet")
    with BunkerDuckDB() as db:
        try:
            n = db.summary_over_parquet(pattern)[0][0]
        except Exception:
            n = 0
    click.echo(
        json.dumps(
            {
                "parquet_glob": pattern,
                "total_rows": int(n),
                "cache_dir": str(paths.cache_root),
                "sync_folder": str(paths.sync_folder()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()