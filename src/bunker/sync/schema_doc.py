from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb


def build_schema_json(parquet_files: list[Path], out_path: Path) -> dict[str, Any]:
    datasets: list[dict[str, Any]] = []
    if not parquet_files:
        doc: dict[str, Any] = {
            "version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "engine": "duckdb",
            "datasets": [],
        }
        out_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return doc
    con = duckdb.connect(database=":memory:")
    try:
        for pf in parquet_files:
            rel_name = pf.stem
            info_rows = con.execute(
                "SELECT * FROM parquet_schema(?)",
                [str(pf)],
            ).fetchall()
            info_cols = [d[0] for d in con.description] if con.description else []
            cols = con.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)",
                [str(pf)],
            ).fetchall()
            datasets.append(
                {
                    "parquet_file": pf.name,
                    "relative_path": pf.name,
                    "columns": [{"name": c[0], "type": c[1]} for c in cols],
                    "parquet_schema": [
                        dict(zip(info_cols, row, strict=False)) for row in info_rows
                    ],
                }
            )
    finally:
        con.close()

    doc: dict[str, Any] = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": "duckdb",
        "datasets": datasets,
    }
    out_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc