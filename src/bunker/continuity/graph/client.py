from __future__ import annotations

import logging
import time
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class TokenProvider(Protocol):
    def get_token(self) -> str:
        """Return a valid Graph access token."""


class HttpxGraphClient:
    """Microsoft Graph client with Retry-After throttling support."""

    def __init__(
        self,
        token_provider: TokenProvider,
        *,
        timeout: float = 60.0,
        max_retries: int = 5,
    ) -> None:
        self._token_provider = token_provider
        self._timeout = timeout
        self._max_retries = max_retries

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self._token_provider.get_token()}"

        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.request(method, url, headers=headers, **kwargs)
                    if resp.status_code == 429:
                        retry = int(resp.headers.get("Retry-After", "2"))
                        logger.warning("Graph 429 — sleeping %ss", retry)
                        time.sleep(min(retry, 120))
                        continue
                    resp.raise_for_status()
                    if not resp.content:
                        return {}
                    data = resp.json()
                    if isinstance(data, dict):
                        return data
                    return {"value": data}
            except (httpx.HTTPError, OSError) as exc:
                last_exc = exc
                backoff = min(2**attempt, 30)
                logger.info("Graph request failed (%s/%s): %s", attempt, self._max_retries, exc)
                time.sleep(backoff)

        if last_exc is not None:
            raise RuntimeError(f"Graph request failed for {path}") from last_exc
        raise RuntimeError(f"Graph request failed for {path}")

    def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("GET", path, **kwargs)

    def get_bytes(self, path: str) -> bytes:
        url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
        headers = {"Authorization": f"Bearer {self._token_provider.get_token()}"}
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", "2"))
                time.sleep(min(retry, 120))
                resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.content