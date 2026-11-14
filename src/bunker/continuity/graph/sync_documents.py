from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from bunker.continuity.encryption import encrypt_at_rest
from bunker.continuity.graph.client import HttpxGraphClient
from bunker.continuity.meta import write_sync_meta
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.storage import write_encrypted_file
from bunker.io.atomic import atomic_write_bytes

logger = logging.getLogger(__name__)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sync_sharepoint_folder(
    paths: ContinuityPaths,
    client: HttpxGraphClient,
    *,
    folder_id: str,
    drive_id: str,
    remote_path: str,
) -> dict[str, Any]:
    paths.ensure()
    dest_root = paths.docs_root / folder_id
    dest_root.mkdir(parents=True, exist_ok=True)

    encoded = remote_path.strip("/").replace("/", ":/")
    api_path = f"/drives/{drive_id}/root:/{encoded}:/children"
    page = client.get(api_path)
    files = [i for i in (page.get("value") or []) if "file" in i]
    manifest_entries: list[dict[str, Any]] = []

    for item in files:
        name = item.get("name", "unnamed")
        item_id = item["id"]
        body = client.get_bytes(f"/drives/{drive_id}/items/{item_id}/content")
        local = dest_root / name
        enc_path = write_encrypted_file(local, body, continuity_root=paths.continuity_root)
        manifest_entries.append(
            {
                "path": str(enc_path.relative_to(paths.continuity_root)),
                "name": name,
                "sha256": _sha256_bytes(body),
                "bytes": len(body),
            }
        )

    manifest = {
        "folder_id": folder_id,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "files": manifest_entries,
    }
    manifest_path = paths.manifest_root / f"{folder_id}.json"
    atomic_write_bytes(
        manifest_path,
        encrypt_at_rest(
            json.dumps(manifest, indent=2).encode(),
            continuity_root=paths.continuity_root,
        ),
    )

    write_sync_meta(
        paths.meta_root,
        f"m365_docs_{folder_id}",
        {"file_count": len(manifest_entries)},
        continuity_root=paths.continuity_root,
    )
    return {"source": f"m365_docs_{folder_id}", "files": len(manifest_entries)}