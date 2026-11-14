from __future__ import annotations

import logging
from typing import Any

from bunker.continuity.notify.outage import notify_outage
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.watch.health import WatchConfig, load_watch_state, run_watch
from bunker.continuity.watch.incident import is_new_down_transition, record_incident

logger = logging.getLogger(__name__)


def watch_once(
    paths: ContinuityPaths,
    cfg: dict[str, Any],
    *,
    graph_client: Any = None,
    probe_override: dict[str, bool] | None = None,
) -> dict[str, Any]:
    cont = cfg.get("continuity", {})
    wcfg = cont.get("watch", {})
    wc = WatchConfig(
        probe_hosts=wcfg.get("probe_hosts", []),
        degraded_after_failures=int(wcfg.get("degraded_after_failures", 2)),
        down_after_failures=int(wcfg.get("down_after_failures", 3)),
        recovery_after_successes=int(wcfg.get("recovery_after_successes", 2)),
        watched_services=wcfg.get(
            "watched_services",
            ["Exchange Online", "Microsoft Teams"],
        ),
        auth_probe_path=wcfg.get("auth_probe_path", "/me/messages?$top=1"),
    )
    prev = load_watch_state(paths.state_file)
    new = run_watch(
        wc,
        paths.state_file,
        graph_client=graph_client,
        probe_override=probe_override,
    )
    incident_path = None
    if is_new_down_transition(prev, new):
        incident_path = record_incident(paths.incidents_root, new)
        notify_outage(cfg, new)
    return {
        "state": new.state.value,
        "probes": new.probes,
        "incident": str(incident_path) if incident_path else None,
    }