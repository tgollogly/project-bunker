from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb


class BunkerDuckDB:
    """Embedded analytics — no external database server."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path
        self._con = duckdb.connect(database=str(db_path) if db_path else ":memory:")

    def close(self) -> None:
        self._con.close()

    def register_parquet_glob(self, name: str, glob_pattern: str) -> None:
        safe = glob_pattern.replace("'", "''")
        sql = (
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_parquet('{safe}', union_by_name=true)"
        )
        self._con.execute(sql)

    def query(self, sql: str, params: list[Any] | None = None) -> duckdb.DuckDBPyRelation:
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