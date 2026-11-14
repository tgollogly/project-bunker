from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ContinuityPaths:
    root: Path
    continuity_root: Path
    parquet_root: Path
    docs_root: Path
    manifest_root: Path
    meta_root: Path
    incidents_root: Path
    state_file: Path

    @classmethod
    def from_config(cls, root: Path, cfg: dict[str, Any]) -> ContinuityPaths:
        cont = cfg.get("continuity", {})
        base = root / cont.get("data_root", "data/continuity")
        return cls(
            root=root,
            continuity_root=base,
            parquet_root=base / "parquet",
            docs_root=base / "docs",
            manifest_root=base / "manifests",
            meta_root=base / "meta",
            incidents_root=base / "incidents",
            state_file=base / "meta" / "watch_state.json",
        )

    def ensure(self) -> None:
        for p in (
            self.parquet_root,
            self.docs_root,
            self.manifest_root,
            self.meta_root,
            self.incidents_root,
        ):
            p.mkdir(parents=True, exist_ok=True)