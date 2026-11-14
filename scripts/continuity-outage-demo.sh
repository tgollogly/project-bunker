#!/usr/bin/env bash
# Simulates M365 probes failing → watch DOWN → Matrix/SMS stub alert → offline web UI
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || make init >/dev/null

export BUNKER_MESH_KEY="${BUNKER_MESH_KEY:-sixteen-byte-key!!}"
export BUNKER_DATA_KEY="${BUNKER_DATA_KEY:-0123456789abcdef0123456789abcdef}"

echo "=== Seed local continuity cache (mock Graph via tests / prior sync) ==="
pytest -q tests/test_continuity_core.py::test_graph_calendar_and_contacts_sync

echo "=== Simulate outage (probes forced down) ==="
python - <<'PY'
import json
from pathlib import Path
from bunker.continuity.config import load_continuity_config
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.watch.run import watch_once

root = Path(".")
cfg = load_continuity_config(root / "config" / "continuity.yaml")
paths = ContinuityPaths.from_config(root, cfg)
# three failing ticks to reach DOWN with default thresholds
for i in range(3):
    out = watch_once(
        paths,
        cfg,
        probe_override={"outlook": False, "teams": False},
    )
    print(f"watch tick {i+1}:", json.dumps(out))
PY

echo "=== Signed LAN alert (HMAC UDP) ==="
python -m bunker.comms.udp_broadcast send "Continuity demo: M365 DOWN — use bunker serve" || true

echo "=== Offline web UI (open http://127.0.0.1:8765 locally) ==="
echo "Run: bunker serve --port 8765"