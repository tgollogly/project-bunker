#!/usr/bin/env bash
# Project Bunker — sub-60s bootstrap (Copyright © 2026 Thomas Gollogly)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  if ! python3 -m venv .venv 2>/dev/null; then
    echo "Install python3-venv (e.g. sudo apt install python3.12-venv) and re-run make init" >&2
    exit 1
  fi
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip wheel >/dev/null
pip install -e ".[dev]" >/dev/null

mkdir -p data/raw data/parquet cache
echo "Bunker ready. Try: make ingest-demo && make sync"