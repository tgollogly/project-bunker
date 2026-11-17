from __future__ import annotations

import pytest

from bunker.sql_ident import validate_sql_identifier


def test_validate_sql_identifier_ok() -> None:
    assert validate_sql_identifier("bunker_data") == "bunker_data"


def test_validate_sql_identifier_rejects_bad() -> None:
    with pytest.raises(ValueError):
        validate_sql_identifier("bad-key")