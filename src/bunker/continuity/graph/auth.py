from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

_REFRESH_MARGIN_SEC = 300


@dataclass
class GraphAuthSettings:
    tenant_id: str
    client_id: str
    client_secret: str | None = None
    scopes: list[str] = field(default_factory=lambda: ["https://graph.microsoft.com/.default"])

    @classmethod
    def from_env(cls) -> GraphAuthSettings | None:
        tenant = os.environ.get("BUNKER_GRAPH_TENANT_ID", "")
        client_id = os.environ.get("BUNKER_GRAPH_CLIENT_ID", "")
        secret = os.environ.get("BUNKER_GRAPH_CLIENT_SECRET")
        if not tenant or not client_id:
            return None
        scopes_raw = os.environ.get("BUNKER_GRAPH_SCOPES", "")
        scopes = [s.strip() for s in scopes_raw.split()] if scopes_raw else [
            "https://graph.microsoft.com/.default"
        ]
        return cls(tenant_id=tenant, client_id=client_id, client_secret=secret, scopes=scopes)


class Clock(Protocol):
    def __call__(self) -> float:
        """Return current Unix timestamp."""


class TokenProvider(Protocol):
    def get_token(self) -> str:
        """Return a valid Graph access token."""

    def invalidate_token(self) -> None:
        """Drop cached token so the next get_token() refreshes."""


class MsalTokenProvider:
    """App-only client credentials with MSAL cache and expiry-aware refresh."""

    def __init__(
        self,
        settings: GraphAuthSettings,
        *,
        clock: Clock | None = None,
    ) -> None:
        if not settings.client_secret:
            raise ValueError("BUNKER_GRAPH_CLIENT_SECRET required for app-only auth")
        self._settings = settings
        self._clock: Clock = clock or time.time
        self._token: str | None = None
        self._expires_at: float = 0.0
        import msal

        self._app = msal.ConfidentialClientApplication(
            self._settings.client_id,
            authority=f"https://login.microsoftonline.com/{self._settings.tenant_id}",
            client_credential=self._settings.client_secret,
        )

    def invalidate_token(self) -> None:
        self._token = None
        self._expires_at = 0.0

    def _acquire(self) -> str:
        result: dict[str, Any] | None = self._app.acquire_token_silent(
            self._settings.scopes,
            account=None,
        )
        if not result:
            result = cast(
                dict[str, Any],
                self._app.acquire_token_for_client(scopes=self._settings.scopes),
            )
        token = result.get("access_token")
        if not token:
            raise RuntimeError(f"MSAL token error: {result.get('error_description', result)}")
        expires_in = int(result.get("expires_in", 3600))
        self._token = cast(str, token)
        self._expires_at = self._clock() + max(expires_in - _REFRESH_MARGIN_SEC, 60)
        return self._token

    def get_token(self) -> str:
        if self._token and self._clock() < self._expires_at:
            return self._token
        return self._acquire()


class StaticTokenProvider:
    """Tests and explicit delegated tokens via BUNKER_GRAPH_ACCESS_TOKEN."""

    def __init__(self, token: str) -> None:
        self._token = token

    def get_token(self) -> str:
        return self._token

    def invalidate_token(self) -> None:
        return None


def build_token_provider() -> MsalTokenProvider | StaticTokenProvider:
    explicit = os.environ.get("BUNKER_GRAPH_ACCESS_TOKEN", "").strip()
    if explicit:
        return StaticTokenProvider(explicit)
    settings = GraphAuthSettings.from_env()
    if settings is None:
        raise RuntimeError(
            "Set BUNKER_GRAPH_* env vars or BUNKER_GRAPH_ACCESS_TOKEN for Graph sync"
        )
    return MsalTokenProvider(settings)