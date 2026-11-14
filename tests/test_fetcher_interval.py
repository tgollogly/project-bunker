from pathlib import Path
from unittest.mock import patch

from bunker.ingest.fetcher import ResilientFetcher


def test_skip_network_when_cache_is_fresh(tmp_path: Path) -> None:
    fetcher = ResilientFetcher(tmp_path)
    fetcher._write_cache("src", b"{}", "application/json")
    assert fetcher.cache_age_seconds("src") is not None

    with patch("httpx.Client.get") as mock_get:
        result = fetcher.fetch("https://example.com/x", "src", min_interval_seconds=3600)
        mock_get.assert_not_called()

    assert result.from_cache is True
    assert result.cache_reason == "fresh"