from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import httpx

from bunker.continuity.graph.client import HttpxGraphClient
from bunker.io.atomic import atomic_write_bytes

logger = logging.getLogger(__name__)


class HealthState(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


@dataclass
class WatchConfig:
    probe_hosts: list[dict[str, str]]
    degraded_after_failures: int = 2
    down_after_failures: int = 3
    recovery_after_successes: int = 2


@dataclass
class WatchState:
    state: HealthState
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    probes: dict[str, bool] | None = None
    updated_at: float = 0.0


def probe_url(url: str, timeout: float = 10.0) -> bool:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            return resp.status_code < 500
    except (httpx.HTTPError, OSError):
        return False


def probe_graph_health(client: HttpxGraphClient | None) -> bool | None:
    if client is None:
        return None
    try:
        client.get("/admin/serviceAnnouncement/healthOverviews")
        return True
    except Exception:
        return False


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
    )


def save_watch_state(path: Path, state: WatchState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "state": state.state.value,
        "consecutive_failures": state.consecutive_failures,
        "consecutive_successes": state.consecutive_successes,
        "probes": state.probes,
        "updated_at": state.updated_at,
    }
    atomic_write_bytes(path, json.dumps(doc, indent=2).encode())


def evaluate_watch(
    cfg: WatchConfig,
    *,
    probe_results: dict[str, bool],
    graph_ok: bool | None,
    prev: WatchState,
) -> WatchState:
    failed = sum(1 for v in probe_results.values() if not v)
    if graph_ok is False:
        failed += 1
    total = len(probe_results) + (1 if graph_ok is not None else 0)
    success = failed == 0 and total > 0

    st = WatchState(
        state=prev.state,
        consecutive_failures=prev.consecutive_failures,
        consecutive_successes=prev.consecutive_successes,
        probes=probe_results,
        updated_at=time.time(),
    )

    if success:
        st.consecutive_successes += 1
        st.consecutive_failures = 0
        if st.state != HealthState.OK and st.consecutive_successes >= cfg.recovery_after_successes:
            st.state = HealthState.OK
        elif st.consecutive_successes >= cfg.recovery_after_successes:
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
            probes[ph["name"]] = probe_url(ph["url"])
    graph_ok = probe_graph_health(graph_client)
    prev = load_watch_state(state_path)
    new_state = evaluate_watch(cfg, probe_results=probes, graph_ok=graph_ok, prev=prev)
    save_watch_state(state_path, new_state)
    return new_state