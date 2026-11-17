from __future__ import annotations

import logging
from typing import Any

from bunker.continuity.graph.auth import build_token_provider
from bunker.continuity.graph.client import HttpxGraphClient
from bunker.continuity.graph.sync_calendars import sync_calendars
from bunker.continuity.graph.sync_contacts import sync_contacts
from bunker.continuity.graph.sync_documents import sync_sharepoint_folder
from bunker.continuity.paths import ContinuityPaths

logger = logging.getLogger(__name__)


class MicrosoftGraphSource:
    """Sync calendar, contacts, and SharePoint folders via Microsoft Graph."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.id = str(entry.get("id", "m365"))

    def sync(self, paths: ContinuityPaths, cfg: dict[str, Any]) -> dict[str, Any]:
        cont = cfg.get("continuity", {})
        client = HttpxGraphClient(build_token_provider())
        graph_cfg = cont.get("graph", {})
        user = graph_cfg.get("calendar_user", "me")
        horizon = int(cont.get("calendar_horizon_days", 14))
        results: list[dict[str, Any]] = []
        results.append(sync_calendars(paths, client, user=user, horizon_days=horizon))
        results.append(sync_contacts(paths, client, user=graph_cfg.get("contact_user", user)))
        for folder in cont.get("sharepoint_folders") or []:
            drive_id = (folder.get("drive_id") or "").strip()
            if not drive_id:
                logger.info("Skipping folder %s — no drive_id", folder.get("id"))
                continue
            try:
                results.append(
                    sync_sharepoint_folder(
                        paths,
                        client,
                        folder_id=folder["id"],
                        drive_id=drive_id,
                        remote_path=folder.get("path", "/"),
                    )
                )
            except Exception as exc:
                logger.error("Document sync failed for %s (local kept): %s", folder.get("id"), exc)
        return {
            "source_id": self.id,
            "type": "microsoft_graph",
            "detail": results,
        }