#!/usr/bin/env bash
# Record with: asciinema rec -c "make walkthrough"
# Offline-first demo (no network required after first ingest cache is seeded)
set -euo pipefail
cd "$(dirname "$0")/.."

export BUNKER_MESH_KEY="${BUNKER_MESH_KEY:-sixteen-byte-key!!}"

echo "=== 1) bootstrap ==="
make init >/dev/null
bunker keygen 2>/dev/null || bunker keygen --force

if [[ ! -f cache/usgs_earthquakes_day.bin ]]; then
  echo "=== 2) live ingest (needs network once) ==="
  bunker ingest --source usgs_earthquakes_day
else
  echo "=== 2) skip live fetch (cache present) ==="
fi

echo "=== 3) simulate outage: ingest from cache only ==="
bunker ingest --source usgs_earthquakes_day --offline

echo "=== 4) package signed sync bundle ==="
SYNC=$(bunker sync-package)
bunker verify-sync "$SYNC" --public-key data/keys/signing.pub.pem

echo "=== 5) import bundle into local lake ==="
bunker import-sync "$SYNC" --public-key data/keys/signing.pub.pem

echo "=== 6) signed LAN alert (UDP broadcast) ==="
python -m bunker.comms.udp_broadcast send "walkthrough complete"

bunker status