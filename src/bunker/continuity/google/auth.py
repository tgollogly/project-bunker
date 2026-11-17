from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from bunker.secrets.store import get_secret

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_REFRESH_MARGIN_SEC = 300


class Clock(Protocol):
    def __call__(self) -> float:
        """Return current Unix timestamp."""


@dataclass
class GoogleOAuthSettings:
    client_id: str
    client_secret: str
    refresh_token: str

    @classmethod
    def from_env(cls) -> GoogleOAuthSettings | None:
        client_id = (
            get_secret("google.client_id") or os.environ.get("BUNKER_GOOGLE_CLIENT_ID", "")
        ).strip()
        client_secret = (
            get_secret("google.client_secret") or os.environ.get("BUNKER_GOOGLE_CLIENT_SECRET", "")
        ).strip()
        refresh = (
            get_secret("google.refresh_token") or os.environ.get("BUNKER_GOOGLE_REFRESH_TOKEN", "")
        ).strip()
        if not client_id or not refresh:
            return None
        if not client_secret:
            client_secret = ""
        return cls(client_id=client_id, client_secret=client_secret, refresh_token=refresh)


class GoogleTokenProvider:
    def __init__(
        self,
        settings: GoogleOAuthSettings,
        *,
        clock: Clock | None = None,
        http: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._clock: Clock = clock or time.time
        self._token: str | None = None
        self._expires_at = 0.0
        self._http = http

    @classmethod
    def from_env(cls) -> GoogleTokenProvider:
        explicit = (
            get_secret("google.access_token") or os.environ.get("BUNKER_GOOGLE_ACCESS_TOKEN", "")
        ).strip()
        if explicit:
            return _StaticGoogleTokenProvider(explicit)
        settings = GoogleOAuthSettings.from_env()
        if settings is None:
            raise RuntimeError(
                "Google sync requires BUNKER_GOOGLE_* tokens or keychain secrets "
                "(client_id + refresh_token at minimum)"
            )
        return cls(settings)

    def invalidate_token(self) -> None:
        self._token = None
        self._expires_at = 0.0

    def _refresh(self) -> str:
        data = {
            "client_id": self._settings.client_id,
            "client_secret": self._settings.client_secret,
            "refresh_token": self._settings.refresh_token,
            "grant_type": "refresh_token",
        }
        if self._http is not None:
            resp = self._http.post(_TOKEN_URL, data=data)
        else:
            with httpx.Client(timeout=30.0) as http:
                resp = http.post(_TOKEN_URL, data=data)
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        token = body.get("access_token")
        if not token:
            raise RuntimeError(f"Google token refresh failed: {json.dumps(body)[:200]}")
        expires_in = int(body.get("expires_in", 3600))
        self._token = str(token)
        self._expires_at = self._clock() + max(expires_in - _REFRESH_MARGIN_SEC, 60)
        return self._token

    def get_token(self) -> str:
        if self._token and self._clock() < self._expires_at:
            return self._token
        return self._refresh()


class _StaticGoogleTokenProvider(GoogleTokenProvider):
    def __init__(self, token: str) -> None:
        super().__init__(GoogleOAuthSettings(client_id="x", client_secret="", refresh_token="x"))
        self._static = token

    def get_token(self) -> str:
        return self._static

    def invalidate_token(self) -> None:
        return None

    def _refresh(self) -> str:
        return self._static