from __future__ import annotations

import logging
from typing import Any

from bunker.continuity.notify.matrix import send_matrix_message
from bunker.continuity.notify.sms import build_sms_provider
from bunker.continuity.watch.health import WatchState

logger = logging.getLogger(__name__)


def notify_outage(cfg: dict[str, Any], watch: WatchState) -> None:
    cont = cfg.get("continuity", {})
    matrix_cfg = cont.get("matrix", {})
    message = (
        f"⚠ Bunker Continuity: Microsoft 365 status {watch.state.value}. "
        "Switch to offline bunker serve and local calendar/contacts."
    )
    try:
        send_matrix_message(
            homeserver=matrix_cfg.get("homeserver", ""),
            room_alias=matrix_cfg.get("room_alias", "#outage:local"),
            message=message,
        )
    except Exception as exc:
        logger.error("Matrix notify failed: %s", exc)

    sms_cfg = cont.get("sms", {})
    try:
        sms = build_sms_provider(sms_cfg.get("provider", "stub"))
        sms.send(message)
    except Exception as exc:
        logger.error("SMS notify failed: %s", exc)