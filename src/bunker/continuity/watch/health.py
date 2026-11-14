from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

from bunker.continuity.graph.client import HttpxGraphClient
from bunker.io.atomic import atomic_write_bytes

logger = logging.getLogger(__name__)

UNHEALTHY_SERVICE_STATUSES = frozenset(
    {
        "servicedegradation",
        "serviceinterruption",
        "extendedrecovery",
        "investigating",
        "restoringservice",
    }
)


class HealthState(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


class ProbeState(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


@dataclass
class WatchConfig:
    probe_hosts: list[dict[str, str]]
    degraded_after_failures: int = 2
    down_after_failures: int = 3
    recovery_after_successes: int = 2
    watched_services: list[str] = field(
        default_factory=lambda: ["Exchange Online", "Microsoft Teams"]
    )
    auth_probe_path: str | None = "/me/messages?$top=1"


@dataclass
class WatchState:
    state: HealthState
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    probes: dict[str, bool] | None = None
    updated_at: float = 0.0
    graph_service_alert: bool = False


def probe_url(url: str, timeout: float = 10.0) -> ProbeState:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code in (401, 403):
                return ProbeState.UP
            if resp.status_code >= 500:
                return ProbeState.DOWN
            return ProbeState.UP if resp.status_code < 500 else ProbeState.DOWN
    except (httpx.HTTPError, OSError):
        return ProbeState.DOWN


def parse_health_overviews(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("value")
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "service": item.get("service"),
                "status": item.get("status"),
            }
        )
    return rows


def unhealthy_watched_services(
    overviews: list[dict[str, Any]],
    watched: list[str],
) -> list[str]:
    watched_lower = {w.lower() for w in watched}
    bad: list[str] = []
    for row in overviews:
        svc = str(row.get("service") or "")
        status = str(row.get("status") or "").lower()
        if svc.lower() in watched_lower and status in UNHEALTHY_SERVICE_STATUSES:
            bad.append(svc)
    return bad


def probe_graph_health(
    client: HttpxGraphClient | None,
    *,
    watched_services: list[str],
) -> tuple[bool | None, bool, list[str]]:
    """Returns (reachable, service_unhealthy_flag, unhealthy_service_names)."""
    if client is None:
        return None, False, []
    try:
        data = client.get("/admin/serviceAnnouncement/healthOverviews")
        overviews = parse_health_overviews(data)
        bad = unhealthy_watched_services(overviews, watched_services)
        return True, bool(bad), bad
    except Exception:
        return False, False, []


def probe_graph_auth_endpoint(client: HttpxGraphClient, path: str) -> ProbeState:
    try:
        client.get(path)
        return ProbeState.UP
    except Exception:
        return ProbeState.DOWN


def load_watch_state(path: Path) -> WatchState:
    if not path.is_file():
        return WatchState(state=HealthState.OK)
    data = json.loads(path.read_text())
    return WatchState(
        state=HealthState(data.get("state", "OK")),
        consecutive_failures=int(data.get("consecutive_failures", 0)),
        consecutive_successes=int(data.get("consecutive_successes", 0)),
        probes=data.get("probes"),
        updated_at=float(data.get("updated_at", 0)),
        graph_service_alert=bool(data.get("graph_service_alert")),
    )


def save_watch_state(path: Path, state: WatchState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "state": state.state.value,
        "consecutive_failures": state.consecutive_failures,
        "consecutive_successes": state.consecutive_successes,
        "probes": state.probes,
        "updated_at": state.updated_at,
        "graph_service_alert": state.graph_service_alert,
    }
    atomic_write_bytes(path, json.dumps(doc, indent=2).encode())


def evaluate_watch(
    cfg: WatchConfig,
    *,
    probe_results: dict[str, bool],
    graph_reachable: bool | None,
    graph_service_unhealthy: bool,
    prev: WatchState,
) -> WatchState:
    signals: list[bool] = list(probe_results.values())
    if graph_reachable is not None:
        signals.append(graph_reachable)
    if graph_service_unhealthy:
        signals.append(False)
    success = bool(signals) and all(signals)

    st = WatchState(
        state=prev.state,
        consecutive_failures=prev.consecutive_failures,
        consecutive_successes=prev.consecutive_successes,
        probes=probe_results,
        updated_at=time.time(),
        graph_service_alert=graph_service_unhealthy,
    )

    if success:
        st.consecutive_successes += 1
        st.consecutive_failures = 0
        if st.state != HealthState.OK and st.consecutive_successes >= cfg.recovery_after_successes:
            st.state = HealthState.OK
    else:
        st.consecutive_failures += 1
        st.consecutive_successes = 0
        if st.consecutive_failures >= cfg.down_after_failures:
            st.state = HealthState.DOWN
        elif st.consecutive_failures >= cfg.degraded_after_failures:
            st.state = HealthState.DEGRADED

    return st


def run_watch(
    cfg: WatchConfig,
    state_path: Path,
    *,
    graph_client: HttpxGraphClient | None = None,
    probe_override: dict[str, bool] | None = None,
) -> WatchState:
    if probe_override is not None:
        probes = probe_override
    else:
        probes = {}
        for ph in cfg.probe_hosts:
            probes[ph["name"]] = probe_url(ph["url"]) == ProbeState.UP
    graph_reachable, graph_unhealthy, _ = probe_graph_health(
        graph_client,
        watched_services=cfg.watched_services,
    )
    if (
        graph_client is not None
        and cfg.auth_probe_path
        and probe_override is None
        and graph_reachable
    ):
        auth_ok = probe_graph_auth_endpoint(graph_client, cfg.auth_probe_path) == ProbeState.UP
        if not auth_ok:
            probes["graph_auth_probe"] = False
        else:
            probes["graph_auth_probe"] = True

    prev = load_watch_state(state_path)
    new_state = evaluate_watch(
        cfg,
        probe_results=probes,
        graph_reachable=graph_reachable,
        graph_service_unhealthy=graph_unhealthy,
        prev=prev,
    )
    save_watch_state(state_path, new_state)
    return new_state