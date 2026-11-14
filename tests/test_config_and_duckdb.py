from pathlib import Path

import pytest

from bunker.config import get_source, load_sources_config
from bunker.duckdb_engine import BunkerDuckDB
from bunker.ingest.parquet_writer import write_rows_parquet_duckdb


def test_config_get_source() -> None:
    cfg = {"sources": [{"id": "a", "url": "x"}]}
    assert get_source(cfg, "a")["id"] == "a"
    with pytest.raises(KeyError):
        get_source(cfg, "missing")


def test_duckdb_register_and_query(tmp_path: Path) -> None:
    p = tmp_path / "t.parquet"
    write_rows_parquet_duckdb([{"n": 1}, {"n": 2}], p)
    with BunkerDuckDB() as db:
        db.register_parquet_glob("t", str(p))
        rows = db.query("SELECT sum(n) FROM t").fetchall()
    assert rows[0][0] == 3


def test_load_project_sources() -> None:
    cfg_path = Path("/workspace/config/sources.yaml")
    if not cfg_path.is_file():
        return
    cfg = load_sources_config(cfg_path)
    assert cfg.get("sources")