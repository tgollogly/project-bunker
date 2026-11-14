from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from bunker.config import get_source, load_sources_config
from bunker.continuity.config import load_continuity_config
from bunker.continuity.encryption import rekey_tree
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.serve.app import create_app
from bunker.continuity.serve.auth import (
    ServeAuthConfig,
    auth_configured,
    loopback_host,
    save_password_hash,
)
from bunker.continuity.status import continuity_status
from bunker.continuity.sync_all import run_continuity_sync
from bunker.continuity.watch.run import watch_once
from bunker.crypto.signing import load_public_key
from bunker.duckdb_engine import BunkerDuckDB
from bunker.ingest.pipeline import ingest_source
from bunker.keys import keygen
from bunker.paths import BunkerPaths
from bunker.sync.import_bundle import import_sync_bundle
from bunker.sync.package import package_airgap_sync
from bunker.sync.verify import verify_sync_folder

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("bunker")


def _project_root() -> Path:
    return Path.cwd()


DEFAULT_CONFIG = "config/sources.yaml"


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=DEFAULT_CONFIG,
)
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
    try:
        out = package_airgap_sync(paths)
    except FileNotFoundError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)
    click.echo(str(out))


@main.command("import-sync")
@click.argument("sync_dir", type=click.Path(path_type=Path, exists=True))
@click.option(
    "--public-key",
    type=click.Path(path_type=Path, exists=True),
    default="data/keys/signing.pub.pem",
)
@click.pass_context
def cmd_import_sync(ctx: click.Context, sync_dir: Path, public_key: Path) -> None:
    paths: BunkerPaths = ctx.obj["paths"]
    pub = load_public_key(public_key)
    try:
        result = import_sync_bundle(sync_dir, paths, public_key=pub)
    except ValueError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)
    click.echo(json.dumps(result, indent=2))


@main.command("keygen")
@click.option("--force", is_flag=True, help="Replace existing key pair")
@click.pass_context
def cmd_keygen(ctx: click.Context, force: bool) -> None:
    paths: BunkerPaths = ctx.obj["paths"]
    try:
        priv, pub = keygen(paths.root, force=force)
    except FileExistsError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)
    click.echo(json.dumps({"private_key": str(priv), "public_key": str(pub)}, indent=2))


@main.command("verify-sync")
@click.argument("sync_dir", type=click.Path(path_type=Path, exists=True))
@click.option(
    "--public-key",
    type=click.Path(path_type=Path, exists=True),
    default="data/keys/signing.pub.pem",
    help="Trusted Ed25519 public key PEM",
)
def cmd_verify_sync(sync_dir: Path, public_key: Path) -> None:
    pub = load_public_key(public_key)
    ok, errors = verify_sync_folder(sync_dir, public_key=pub, require_signature=True)
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


def _continuity_cfg() -> tuple[ContinuityPaths, dict]:
    root = _project_root()
    cfg_path = root / "config" / "continuity.yaml"
    cfg = load_continuity_config(cfg_path)
    paths = ContinuityPaths.from_config(root, cfg)
    return paths, cfg


@main.group()
def continuity() -> None:
    """Bunker Continuity — Microsoft 365 outage resilience."""


@continuity.command("sync")
@click.pass_context
def cmd_continuity_sync(ctx: click.Context) -> None:
    paths, cfg = _continuity_cfg()
    try:
        results = run_continuity_sync(paths, cfg)
    except Exception as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
    click.echo(json.dumps(results, indent=2))


@continuity.command("status")
@click.pass_context
def cmd_continuity_status(ctx: click.Context) -> None:
    paths, _cfg = _continuity_cfg()
    click.echo(json.dumps(continuity_status(paths), indent=2))


@continuity.command("rekey")
@click.pass_context
def cmd_continuity_rekey(ctx: click.Context) -> None:
    paths, _cfg = _continuity_cfg()
    try:
        count = rekey_tree(paths.continuity_root)
    except RuntimeError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
    click.echo(json.dumps({"rekeyed_files": count}, indent=2))


@main.group(invoke_without_command=True)
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8765)
@click.option("--certfile", type=click.Path(path_type=Path), default=None)
@click.option("--keyfile", type=click.Path(path_type=Path), default=None)
@click.pass_context
def serve(
    ctx: click.Context,
    host: str,
    port: int,
    certfile: Path | None,
    keyfile: Path | None,
) -> None:
    """Offline continuity web UI."""
    if ctx.invoked_subcommand is not None:
        return
    paths, cfg = _continuity_cfg()
    auth_path = paths.continuity_root / "serve_auth.json"
    if not loopback_host(host) and not auth_configured(auth_path):
        click.echo(
            "ERROR: non-loopback serve requires authentication — "
            "run `bunker serve set-password` first",
            err=True,
        )
        sys.exit(1)
    if not loopback_host(host) and certfile is None:
        click.echo(
            "WARNING: serving on LAN without TLS (--certfile/--keyfile) "
            "exposes traffic in cleartext",
            err=True,
        )
    import uvicorn

    auth = (
        ServeAuthConfig(auth_path=auth_path, secure_cookie=certfile is not None)
        if not loopback_host(host)
        else None
    )
    app = create_app(paths, cfg, bind_host=host, auth=auth)
    ssl_kwargs: dict = {}
    if certfile and keyfile:
        ssl_kwargs = {"ssl_certfile": str(certfile), "ssl_keyfile": str(keyfile)}
    uvicorn.run(app, host=host, port=port, log_level="info", **ssl_kwargs)


@serve.command("set-password")
@click.password_option(confirmation_prompt=True)
@click.pass_context
def cmd_serve_set_password(ctx: click.Context, password: str) -> None:
    paths, _cfg = _continuity_cfg()
    auth_path = paths.continuity_root / "serve_auth.json"
    save_password_hash(auth_path, password)
    click.echo(f"Saved serve password hash at {auth_path}")


@main.command("watch")
@click.pass_context
def cmd_watch(ctx: click.Context) -> None:
    paths, cfg = _continuity_cfg()
    result = watch_once(paths, cfg, graph_client=None)
    click.echo(json.dumps(result, indent=2))


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