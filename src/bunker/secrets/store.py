"""OS keychain storage with BUNKER_* environment variable fallback."""
from __future__ import annotations

import logging
import os
from typing import Final

logger = logging.getLogger(__name__)

SERVICE_NAME: Final = "project-bunker"

# logical name -> environment variable used when keyring is empty/unavailable
SECRET_ENV_FALLBACK: dict[str, str] = {
    "data_key": "BUNKER_DATA_KEY",
    "data_key_new": "BUNKER_DATA_KEY_NEW",
    "graph.tenant_id": "BUNKER_GRAPH_TENANT_ID",
    "graph.client_id": "BUNKER_GRAPH_CLIENT_ID",
    "graph.client_secret": "BUNKER_GRAPH_CLIENT_SECRET",
    "graph.access_token": "BUNKER_GRAPH_ACCESS_TOKEN",
    "google.client_id": "BUNKER_GOOGLE_CLIENT_ID",
    "google.client_secret": "BUNKER_GOOGLE_CLIENT_SECRET",
    "google.refresh_token": "BUNKER_GOOGLE_REFRESH_TOKEN",
    "google.access_token": "BUNKER_GOOGLE_ACCESS_TOKEN",
    "mesh_key": "BUNKER_MESH_KEY",
    "matrix.access_token": "BUNKER_MATRIX_ACCESS_TOKEN",
}


def _env_for(name: str) -> str:
    return SECRET_ENV_FALLBACK.get(name, f"BUNKER_{name.upper().replace('.', '_')}")


def _keyring_get(name: str) -> str | None:
    try:
        import keyring

        val = keyring.get_password(SERVICE_NAME, name)
        if val:
            return val
    except Exception as exc:
        logger.debug("keyring get failed for %s: %s", name, exc)
    return None


def _keyring_set(name: str, value: str) -> bool:
    try:
        import keyring

        backend = keyring.get_keyring()
        backend_name = backend.__class__.__name__
        if backend_name in ("FailKeyring", "NoKeyringBackend"):
            return False
        keyring.set_password(SERVICE_NAME, name, value)
        return True
    except Exception as exc:
        logger.warning("keyring set failed for %s: %s", name, exc)
        return False


def _keyring_delete(name: str) -> bool:
    try:
        import keyring

        keyring.delete_password(SERVICE_NAME, name)
        return True
    except Exception:
        return False


def get_secret(name: str) -> str | None:
    """Return a secret from the OS keychain, else from the mapped env var."""
    kr = _keyring_get(name)
    if kr is not None:
        return kr
    env = _env_for(name)
    raw = os.environ.get(env, "").strip()
    return raw or None


def set_secret(name: str, value: str, *, prefer_keyring: bool = True) -> None:
    if prefer_keyring and _keyring_set(name, value):
        return
    os.environ[_env_for(name)] = value


def delete_secret(name: str) -> None:
    _keyring_delete(name)


def list_stored_secret_names() -> list[str]:
    """Names with keyring entries (best-effort; backend-dependent)."""
    try:
        import keyring

        backend = keyring.get_keyring()
        if hasattr(backend, "get_password") and hasattr(backend, "_service"):
            return []
    except Exception:
        pass
    return sorted(SECRET_ENV_FALLBACK)


def inject_secrets_into_environ(names: tuple[str, ...] = tuple(SECRET_ENV_FALLBACK)) -> None:
    """Populate os.environ from keychain for Graph/Google sync (no overwrite if set)."""
    for name in names:
        env = _env_for(name)
        if os.environ.get(env, "").strip():
            continue
        val = _keyring_get(name)
        if val:
            os.environ[env] = val