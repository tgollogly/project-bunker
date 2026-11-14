from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from bunker.continuity.encryption import decrypt_at_rest, encrypt_at_rest
from bunker.io.atomic import atomic_write_bytes

ENCRYPTED_PARQUET_SUFFIX = ".parquet.enc"


def encrypted_parquet_path(base_part: Path) -> Path:
    return base_part.with_suffix(ENCRYPTED_PARQUET_SUFFIX)


def write_encrypted_parquet_rows(
    rows: list[dict[str, Any]],
    dest: Path,
    *,
    continuity_root: Path,
) -> Path:
    if not rows:
        raise ValueError("write_encrypted_parquet_rows requires at least one row")
    dest = encrypted_parquet_path(dest) if dest.suffix != ENCRYPTED_PARQUET_SUFFIX else dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows), buf, compression="zstd")
    atomic_write_bytes(dest, encrypt_at_rest(buf.getvalue(), continuity_root=continuity_root))
    return dest


def iter_encrypted_parquet_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(root.glob(f"**/*{ENCRYPTED_PARQUET_SUFFIX}"))


def read_decrypted_table(path: Path, *, continuity_root: Path) -> pa.Table:
    raw = decrypt_at_rest(path.read_bytes(), continuity_root=continuity_root)
    return pq.read_table(io.BytesIO(raw))


def query_rows_from_root(
    root: Path,
    columns: list[str],
    *,
    order_by: str,
    limit: int,
    continuity_root: Path,
) -> list[tuple[Any, ...]]:
    files = iter_encrypted_parquet_files(root)
    if not files:
        return []
    tables = [read_decrypted_table(p, continuity_root=continuity_root) for p in files]
    combined = pa.concat_tables(tables, promote_options="default")
    names = combined.column_names
    pick = [n for n in columns if n in names]
    if not pick:
        return []
    sub = combined.select(pick)
    py_rows = sub.to_pylist()
    py_rows.sort(key=lambda r: str(r.get(order_by) or ""))
    out: list[tuple[Any, ...]] = []
    for row in py_rows[:limit]:
        out.append(tuple(row.get(c) for c in pick))
    return out