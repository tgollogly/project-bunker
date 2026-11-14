#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

export BUNKER_MESH_KEY="${BUNKER_MESH_KEY:-sixteen-byte-key!!}"
export BUNKER_DATA_KEY="${BUNKER_DATA_KEY:-0123456789abcdef0123456789abcdef}"

PYTHON="${PYTHON:-python3}"
"$PYTHON" -m pip install -U pip
"$PYTHON" -m pip install -e ".[dev]"
export PATH="$(pwd)/.venv/bin:${PATH}"
if ! command -v bunker >/dev/null 2>&1; then
  export PATH="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_path("scripts"))'):$PATH"
fi

bunker keygen --force

bash scripts/continuity-outage-demo.sh

WATCH_JSON=$("$PYTHON" -c "
import json
from pathlib import Path
from bunker.continuity.config import load_continuity_config
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.watch.health import load_watch_state

root = Path('.')
cfg = load_continuity_config(root / 'config' / 'continuity.yaml')
paths = ContinuityPaths.from_config(root, cfg)
print(json.dumps({'state': load_watch_state(paths.state_file).state.value}))
")
echo "watch state: $WATCH_JSON"
echo "$WATCH_JSON" | grep -q '"state": "DOWN"'

INCIDENT_COUNT=$(find data/continuity/incidents -name '*.json' 2>/dev/null | wc -l)
test "$INCIDENT_COUNT" -ge 1

PORT=18880
bunker serve --port "$PORT" &
SERVE_PID=$!
trap 'kill "$SERVE_PID" 2>/dev/null || true' EXIT
sleep 3

curl -sf "http://127.0.0.1:${PORT}/" | tee /tmp/bunker-home.html
grep -q 'DOWN' /tmp/bunker-home.html
grep -q 'Sam Sampleton' /tmp/bunker-home.html

SYNC_DIR=$(bunker sync-package)
bunker verify-sync "$SYNC_DIR"

echo "smoke OK"