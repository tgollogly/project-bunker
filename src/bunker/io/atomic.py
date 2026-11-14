from __future__ import annotations

import os
from pathlib import Path


def atomic_write_bytes(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, dest)
    finally:
        if tmp.exists() and tmp != dest:
            tmp.unlink(missing_ok=True)


def atomic_write_text(dest: Path, text: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(dest, text.encode(encoding))