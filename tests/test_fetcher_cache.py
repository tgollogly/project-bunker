from pathlib import Path
from unittest.mock import patch

import httpx

from bunker.ingest.fetcher import ResilientFetcher


def test_fetcher_uses_cache_when_network_fails(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    fetcher = ResilientFetcher(cache)
    fetcher._write_cache("demo", b'{"ok": true}', "application/json")

    with patch("httpx.Client.get", side_effect=httpx.ConnectError("partition")):
        result = fetcher.fetch(
            "https://example.invalid/data",
            "demo",
            min_interval_seconds=0,
        )

    assert result.from_cache is True
    assert result.cache_reason == "fallback"
    assert result.payload == b'{"ok": true}'