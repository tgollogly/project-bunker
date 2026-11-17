from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from bunker.sql_ident import validate_sql_identifier


class BunkerDuckDB:
    """Embedded analytics — no external database server."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path
        self._con = duckdb.connect(database=str(db_path) if db_path else ":memory:")

    def close(self) -> None:
        self._con.close()

    def register_parquet_glob(self, name: str, glob_pattern: str) -> None:
        view = validate_sql_identifier(name, label="view name")
        safe_glob = glob_pattern.replace("'", "''")
        view_sql = (
            "CREATE OR REPLACE VIEW "
            + view
            + " AS SELECT * FROM read_parquet('"
            + safe_glob
            + "', union_by_name=true)"
        )
        self._con.execute(view_sql)

    def query(self, sql: str, params: list[Any] | None = None) -> duckdb.DuckDBPyConnection:
        if params:
            return self._con.execute(sql, params)
        return self._con.execute(sql)

    def summary_over_parquet(self, glob_pattern: str) -> list[tuple]:
        return self._con.execute(
            "SELECT COUNT(*) AS n FROM read_parquet(?)",
            [glob_pattern],
        ).fetchall()

    def __enter__(self) -> BunkerDuckDB:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()