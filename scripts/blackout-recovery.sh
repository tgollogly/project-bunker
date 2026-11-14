#!/usr/bin/env bash
# Worst-case: global internet / cloud outage — operate from cache + P2P sync only
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate

echo "== Blackout mode: ingest from cache only =="
bunker ingest-all --offline || true

SYNC_DIR="${1:-}"
if [[ -n "$SYNC_DIR" && -d "$SYNC_DIR" ]]; then
  echo "== Importing peer sync bundle: $SYNC_DIR =="
  bunker verify-sync "$SYNC_DIR"
  mkdir -p data/parquet/imported
  cp -a "$SYNC_DIR/shards/"*.parquet data/parquet/imported/ 2>/dev/null || true
fi

bunker status
echo "Query offline: bunker query 'SELECT COUNT(*) FROM bunker_data'"