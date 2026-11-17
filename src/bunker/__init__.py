"""Project Bunker — resilient local data engine and Bunker Continuity."""

from __future__ import annotations


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("bunker")
    except Exception:
        return "0.4.2"


__version__ = _package_version()