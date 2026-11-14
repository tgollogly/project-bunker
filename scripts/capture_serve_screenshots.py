#!/usr/bin/env python3
"""Seed demo continuity data, capture bunker serve UI screenshots (Playwright)."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "images"


def _seed() -> None:
    os.chdir(ROOT)
    os.environ.setdefault("BUNKER_MESH_KEY", "sixteen-byte-key!!")
    os.environ.setdefault(
        "BUNKER_DATA_KEY",
        os.environ.get("BUNKER_DATA_KEY", "0123456789abcdef0123456789abcdef"),
    )
    subprocess.check_call(
        [sys.executable, "-m", "bunker.cli", "continuity", "seed-sample"],
        env=os.environ,
    )
    subprocess.check_call(
        [
            sys.executable,
            "-c",
            """
from pathlib import Path
import json
from bunker.continuity.config import load_continuity_config
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.watch.run import watch_once

root = Path('.')
cfg = load_continuity_config(root / 'config' / 'continuity.yaml')
paths = ContinuityPaths.from_config(root, cfg)
for i in range(3):
    out = watch_once(paths, cfg, probe_override={'outlook': False, 'teams': False})
    print(json.dumps(out))
""",
        ],
    )


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "-q"])
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        from playwright.sync_api import sync_playwright

    _seed()
    DOCS.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [sys.executable, "-m", "bunker.cli", "serve", "--port", "18765"],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": str(ROOT / ".venv" / "bin") + os.pathsep + os.environ.get("PATH", ""),
        },
    )
    try:
        time.sleep(2)
        base = "http://127.0.0.1:18765"
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(f"{base}/status", wait_until="networkidle")
            page.screenshot(path=str(DOCS / "screenshot-dashboard.png"), full_page=True)
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    print(f"Wrote {DOCS / 'screenshot-dashboard.png'}")


if __name__ == "__main__":
    main()