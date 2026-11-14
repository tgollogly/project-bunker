from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, cast


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


class MsalTokenProvider:
    """App-only client credentials when client secret is set."""

    def __init__(self, settings: GraphAuthSettings) -> None:
        if not settings.client_secret:
            raise ValueError("BUNKER_GRAPH_CLIENT_SECRET required for app-only auth")
        self._settings = settings
        self._token: str | None = None

    def get_token(self) -> str:
        if self._token:
            return self._token
        import msal

        app = msal.ConfidentialClientApplication(
            self._settings.client_id,
            authority=f"https://login.microsoftonline.com/{self._settings.tenant_id}",
            client_credential=self._settings.client_secret,
        )
        result: dict[str, Any] = app.acquire_token_for_client(scopes=self._settings.scopes)
        token = result.get("access_token")
        if not token:
            raise RuntimeError(f"MSAL token error: {result.get('error_description', result)}")
        self._token = token
        return cast(str, token)


class StaticTokenProvider:
    """Tests and explicit delegated tokens via BUNKER_GRAPH_ACCESS_TOKEN."""

    def __init__(self, token: str) -> None:
        self._token = token

    def get_token(self) -> str:
        return self._token


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