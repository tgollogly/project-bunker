from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from bunker.io.atomic import atomic_write_bytes


@dataclass
class SetupState:
    completed: bool = False
    selected_sources: list[str] = field(default_factory=list)
    sync_interval_hours: int = 6
    encryption_passphrase_set: bool = False
    notes: dict[str, Any] = field(default_factory=dict)


def setup_state_path(continuity_root: Path) -> Path:
    return continuity_root / "setup_state.json"


def load_setup_state(continuity_root: Path) -> SetupState:
    path = setup_state_path(continuity_root)
    if not path.is_file():
        return SetupState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return SetupState()
    if not isinstance(data, dict):
        return SetupState()
    return SetupState(
        completed=bool(data.get("completed")),
        selected_sources=list(data.get("selected_sources") or []),
        sync_interval_hours=int(data.get("sync_interval_hours", 6)),
        encryption_passphrase_set=bool(data.get("encryption_passphrase_set")),
        notes=dict(data.get("notes") or {}),
    )


def save_setup_state(continuity_root: Path, state: SetupState) -> None:
    continuity_root.mkdir(parents=True, exist_ok=True)
    path = setup_state_path(continuity_root)
    atomic_write_bytes(path, json.dumps(asdict(state), indent=2).encode("utf-8"))