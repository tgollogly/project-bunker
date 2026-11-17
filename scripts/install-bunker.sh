#!/usr/bin/env bash
# One-line install for Linux/macOS: pipx + bunker CLI
set -euo pipefail
if ! command -v pipx >/dev/null 2>&1; then
  python3 -m pip install --user pipx
  python3 -m pipx ensurepath
fi
pipx install --force "git+https://github.com/tgollogly/project-bunker.git"
echo "Installed. Run: bunker --help"
echo "Quick demo: bunker continuity seed-sample && bunker serve --port 8765"