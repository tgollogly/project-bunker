from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class BunkerPaths:
    root: Path
    data_root: Path
    cache_root: Path
    parquet_root: Path
    raw_root: Path
    sync_root: Path

    @classmethod
    def from_config(cls, root: Path, cfg: dict) -> BunkerPaths:
        bunker = cfg.get("bunker", {})
        data = root / bunker.get("data_root", "data")
        cache = root / bunker.get("cache_root", "cache")
        sync = root / bunker.get("sync_root", ".")
        return cls(
            root=root,
            data_root=data,
            cache_root=cache,
            parquet_root=data / "parquet",
            raw_root=data / "raw",
            sync_root=sync,
        )

    def ensure(self) -> None:
        self.parquet_root.mkdir(parents=True, exist_ok=True)
        self.raw_root.mkdir(parents=True, exist_ok=True)
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def sync_folder(self, on: date | None = None) -> Path:
        d = on or date.today()
        return self.sync_root / f"bunker_sync_{d.isoformat()}"