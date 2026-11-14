from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


def send_matrix_message(
    *,
    homeserver: str,
    room_alias: str,
    message: str,
    access_token: str | None = None,
) -> None:
    token = access_token or os.environ.get("BUNKER_MATRIX_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BUNKER_MATRIX_ACCESS_TOKEN required for Matrix alerts")

    hs = homeserver.rstrip("/")
    alias = room_alias if room_alias.startswith("#") else f"#{room_alias}"
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=30.0) as client:
        room_resp = client.get(
            f"{hs}/_matrix/client/v3/directory/room/{alias}",
            headers=headers,
        )
        room_resp.raise_for_status()
        room_id = room_resp.json()["room_id"]
        txn_id = os.urandom(8).hex()
        body = {
            "msgtype": "m.text",
            "body": message,
        }
        send = client.put(
            f"{hs}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}",
            headers=headers,
            json=body,
        )
        send.raise_for_status()
    logger.info("Matrix alert sent to %s", alias)