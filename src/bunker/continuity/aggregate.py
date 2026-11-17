"""Merge calendar and contact rows across pluggable source partitions."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from bunker.continuity.parquet_io import iter_encrypted_parquet_files, query_rows_from_root
from bunker.continuity.paths import ContinuityPaths


def _calendar_roots(parquet_root: Path) -> list[Path]:
    roots: list[Path] = []
    if not parquet_root.is_dir():
        return roots
    for cal in sorted(parquet_root.rglob("calendar")):
        if cal.is_dir() and iter_encrypted_parquet_files(cal):
            roots.append(cal)
    return roots


def _contact_roots(parquet_root: Path) -> list[Path]:
    roots: list[Path] = []
    if not parquet_root.is_dir():
        return roots
    for contacts in sorted(parquet_root.rglob("contacts")):
        if contacts.is_dir() and iter_encrypted_parquet_files(contacts):
            roots.append(contacts)
    return roots


def query_all_calendar_rows(
    paths: ContinuityPaths,
    *,
    columns: list[str],
    order_by: str = "start",
    limit: int = 200,
) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for root in _calendar_roots(paths.parquet_root):
        rows.extend(
            query_rows_from_root(
                root,
                columns,
                order_by=order_by,
                limit=limit,
                continuity_root=paths.continuity_root,
            )
        )
    rows.sort(key=lambda r: str(r[1] if len(r) > 1 else ""))
    return rows[:limit]


def query_all_contact_rows(
    paths: ContinuityPaths,
    *,
    columns: list[str],
    order_by: str = "display_name",
    limit: int = 500,
) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for root in _contact_roots(paths.parquet_root):
        rows.extend(
            query_rows_from_root(
                root,
                columns,
                order_by=order_by,
                limit=limit,
                continuity_root=paths.continuity_root,
            )
        )
    rows.sort(key=lambda r: str(r[0] if r else ""))
    return rows[:limit]