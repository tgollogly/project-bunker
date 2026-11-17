from __future__ import annotations

import logging
from typing import Any, Protocol

from bunker.continuity.paths import ContinuityPaths
from bunker.secrets.store import inject_secrets_into_environ

logger = logging.getLogger(__name__)


class ContinuitySource(Protocol):
    id: str

    def sync(self, paths: ContinuityPaths, cfg: dict[str, Any]) -> dict[str, Any]:
        """Return a sync result dict with source_id and details."""


def _default_source_entries(cont: dict[str, Any]) -> list[dict[str, Any]]:
    if cont.get("sync_sources"):
        return list(cont["sync_sources"])
    # backward compatibility: implicit Microsoft Graph source
    return [{"id": "m365", "type": "microsoft_graph", "enabled": True}]


def _build_source(entry: dict[str, Any]) -> ContinuitySource | None:
    if not entry.get("enabled", True):
        return None
    stype = str(entry.get("type", "")).strip().lower()
    if stype == "microsoft_graph":
        from bunker.continuity.sources.microsoft_graph import MicrosoftGraphSource

        return MicrosoftGraphSource(entry)
    if stype == "google_workspace":
        from bunker.continuity.sources.google_workspace import GoogleWorkspaceSource

        return GoogleWorkspaceSource(entry)
    if stype == "ical":
        from bunker.continuity.sources.ical_source import IcalSource

        return IcalSource(entry)
    if stype == "contacts_file":
        from bunker.continuity.sources.contacts_file import ContactsFileSource

        return ContactsFileSource(entry)
    if stype == "local_folder":
        from bunker.continuity.sources.local_folder import LocalFolderSource

        return LocalFolderSource(entry)
    logger.warning("Unknown continuity source type %r — skipped", stype)
    return None


def run_configured_sources(paths: ContinuityPaths, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    cont = cfg.get("continuity", {})
    inject_secrets_into_environ()
    results: list[dict[str, Any]] = []
    for entry in _default_source_entries(cont):
        src = _build_source(entry)
        if src is None:
            continue
        try:
            results.append(src.sync(paths, cfg))
        except Exception as exc:
            logger.error("Source %s failed (local copies kept): %s", entry.get("id"), exc)
            raise
    return results