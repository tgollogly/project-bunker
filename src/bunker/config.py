from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_sources_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid config at {path}")
    return data


def get_source(cfg: dict[str, Any], source_id: str) -> dict[str, Any]:
    for src in cfg.get("sources", []):
        if src.get("id") == source_id:
            return src
    raise KeyError(f"Unknown source id: {source_id}")