from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    payload: bytes
    content_type: str | None
    from_cache: bool
    source_path: Path
    cache_reason: Literal["network", "fresh", "fallback"] = "network"


class ResilientFetcher:
    """Fetch open-data endpoints with cache fallback (no unhandled network failures)."""

    def __init__(self, cache_dir: Path, timeout: float = 30.0, max_retries: int = 3) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.max_retries = max_retries

    def _cache_path(self, cache_key: str) -> Path:
        return self.cache_dir / f"{cache_key}.bin"

    def _meta_path(self, cache_key: str) -> Path:
        return self.cache_dir / f"{cache_key}.meta.json"

    def cache_age_seconds(self, cache_key: str) -> float | None:
        meta_path = self._meta_path(cache_key)
        if not meta_path.is_file():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        fetched_at = meta.get("fetched_at")
        if fetched_at is None:
            return None
        return time.time() - float(fetched_at)

    def _write_cache(self, cache_key: str, body: bytes, content_type: str | None) -> Path:
        path = self._cache_path(cache_key)
        path.write_bytes(body)
        meta = {
            "content_type": content_type,
            "fetched_at": time.time(),
            "size": len(body),
        }
        self._meta_path(cache_key).write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return path

    def _read_cache(
        self, cache_key: str, *, reason: Literal["fresh", "fallback"] = "fallback"
    ) -> FetchResult | None:
        path = self._cache_path(cache_key)
        if not path.is_file():
            return None
        meta: dict[str, Any] = {}
        meta_path = self._meta_path(cache_key)
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if reason == "fallback":
            logger.warning(
                "Network unavailable or request failed — using cached snapshot %s", path
            )
        else:
            logger.info("Skipping network fetch; cache still fresh for %s", cache_key)
        return FetchResult(
            payload=path.read_bytes(),
            content_type=meta.get("content_type"),
            from_cache=True,
            source_path=path,
            cache_reason=reason,
        )

    def fetch(
        self,
        url: str,
        cache_key: str,
        min_interval_seconds: float = 0,
    ) -> FetchResult:
        """GET *url*; on failure return last good cache. Never raises on network partition."""
        if min_interval_seconds > 0:
            age = self.cache_age_seconds(cache_key)
            if age is not None and age < min_interval_seconds:
                fresh = self._read_cache(cache_key, reason="fresh")
                if fresh is not None:
                    return fresh

        last_attempt: Exception | None = None
        backoff = 1.0

        for attempt in range(1, self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                    resp = client.get(
                        url,
                        headers={
                            "User-Agent": "ProjectBunker/0.2 (+offline-first; Thomas Gollogly)",
                        },
                    )
                    resp.raise_for_status()
                    body = resp.content
                    ctype = resp.headers.get("content-type")
                    path = self._write_cache(cache_key, body, ctype)
                    return FetchResult(
                        payload=body,
                        content_type=ctype,
                        from_cache=False,
                        source_path=path,
                        cache_reason="network",
                    )
            except (httpx.HTTPError, OSError) as exc:
                last_attempt = exc
                logger.info("Fetch attempt %s/%s failed: %s", attempt, self.max_retries, exc)
                time.sleep(backoff)
                backoff = min(backoff * 2, 8.0)

        cached = self._read_cache(cache_key, reason="fallback")
        if cached is not None:
            return cached

        if last_attempt is not None:
            logger.error("No cache for %s after failed fetch", cache_key)
        raise RuntimeError(
            f"Could not fetch {url} and no local cache exists for key '{cache_key}'"
        )