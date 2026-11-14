from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

ParserFn = Callable[[bytes], list[dict[str, Any]]]

_REGISTRY: dict[str, ParserFn] = {}


def register_parser(name: str, fn: ParserFn) -> None:
    _REGISTRY[name] = fn


def get_parser(name: str) -> ParserFn:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(f"Unknown parser '{name}'. Registered: {known}") from exc


def resolve_parser(source: dict[str, Any]) -> ParserFn:
    name = source.get("parser")
    if name:
        return get_parser(name)
    sid = source["id"]
    if sid in _REGISTRY:
        return get_parser(sid)
    fmt = source.get("format")
    if fmt and fmt in _REGISTRY:
        return get_parser(fmt)
    raise KeyError(
        f"Source {sid!r} has no parser. Set parser: in config or register parser for id/format."
    )


def _parse_usgs_geojson(payload: bytes) -> list[dict[str, Any]]:
    doc = json.loads(payload)
    features = doc.get("features") or []
    rows: list[dict[str, Any]] = []
    for feat in features:
        props = dict(feat.get("properties") or {})
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or [None, None, None]
        props["_lon"] = coords[0] if len(coords) > 0 else None
        props["_lat"] = coords[1] if len(coords) > 1 else None
        props["_depth_km"] = coords[2] if len(coords) > 2 else None
        props["_feature_id"] = feat.get("id")
        rows.append(props)
    return rows


def _parse_open_meteo_hourly(payload: bytes) -> list[dict[str, Any]]:
    doc = json.loads(payload)
    hourly = doc.get("hourly") or {}
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    rows: list[dict[str, Any]] = []
    for i, t in enumerate(times):
        rows.append(
            {
                "time": t,
                "temperature_2m": temps[i] if i < len(temps) else None,
                "latitude": doc.get("latitude"),
                "longitude": doc.get("longitude"),
            }
        )
    return rows


register_parser("usgs_earthquakes_day", _parse_usgs_geojson)
register_parser("geojson", _parse_usgs_geojson)
register_parser("open_meteo_hourly", _parse_open_meteo_hourly)
register_parser("open_meteo_demo", _parse_open_meteo_hourly)