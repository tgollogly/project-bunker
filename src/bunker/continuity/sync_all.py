from __future__ import annotations

import logging
from typing import Any

from bunker.continuity.encryption import EncryptionRequiredError, ensure_encryption_key
from bunker.continuity.outage_pack import generate_outage_pack_pdf
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.sources.registry import run_configured_sources

logger = logging.getLogger(__name__)


def run_continuity_sync(paths: ContinuityPaths, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Sync configured continuity sources. On failure, leaves existing local data untouched."""
    try:
        ensure_encryption_key(cfg, paths.continuity_root)
    except EncryptionRequiredError:
        raise
    results = run_configured_sources(paths, cfg)
    try:
        cont = cfg.get("continuity", {})
        if cont.get("outage_pack", True):
            days = int(cont.get("outage_pack_days", 7))
            generate_outage_pack_pdf(paths, days=days)
    except Exception as exc:
        logger.warning("Outage pack PDF generation failed (sync otherwise OK): %s", exc)
    return results