from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from bunker.continuity.watch.health import HealthState, WatchState
from bunker.io.atomic import atomic_write_bytes


def record_incident(incidents_root: Path, watch: WatchState) -> Path:
    incidents_root.mkdir(parents=True, exist_ok=True)
    incident_id = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    doc = {
        "id": incident_id,
        "state": watch.state.value,
        "probes": watch.probes,
        "recorded_at": time.time(),
        "note": "Microsoft 365 reachability check reported DOWN",
    }
    path = incidents_root / f"{incident_id}.json"
    atomic_write_bytes(path, json.dumps(doc, indent=2).encode())
    return path


def is_new_down_transition(prev: WatchState, new: WatchState) -> bool:
    return new.state == HealthState.DOWN and prev.state != HealthState.DOWN