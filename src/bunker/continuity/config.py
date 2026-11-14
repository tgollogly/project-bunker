from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, cast

import yaml

_ENV_PATTERN = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}")


def _expand_env(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        default = match.group(2)
        return os.environ.get(key, default or "")

    return _ENV_PATTERN.sub(repl, value)


def _expand_tree(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _expand_tree(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_tree(v) for v in obj]
    if isinstance(obj, str):
        return _expand_env(obj)
    return obj


def load_continuity_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid continuity config at {path}")
    expanded = _expand_tree(data)
    return cast(dict[str, Any], expanded)