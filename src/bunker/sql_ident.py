"""Validate names that are embedded in DuckDB SQL (not user SQL)."""
from __future__ import annotations

import re

_SQL_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_sql_identifier(name: str, *, label: str = "identifier") -> str:
    if not _SQL_IDENT.fullmatch(name):
        raise ValueError(f"invalid SQL {label}: {name!r}")
    return name