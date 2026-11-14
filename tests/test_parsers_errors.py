import pytest

from bunker.ingest.parsers import resolve_parser


def test_unknown_parser_raises() -> None:
    with pytest.raises(KeyError):
        resolve_parser({"id": "nope", "format": "xml"})