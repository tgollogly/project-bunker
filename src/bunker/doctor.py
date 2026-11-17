from __future__ import annotations

import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from bunker.config import load_sources_config
from bunker.continuity.config import load_continuity_config
from bunker.continuity.encryption import encryption_available
from bunker.continuity.paths import ContinuityPaths
from bunker.paths import BunkerPaths
from bunker.secrets.store import get_secret, inject_secrets_into_environ


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _check_sources_config(root: Path) -> CheckResult:
    path = root / "config" / "sources.yaml"
    if not path.is_file():
        return CheckResult("sources.yaml", False, f"missing: {path}")
    try:
        load_sources_config(path)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        return CheckResult("sources.yaml", False, str(exc))
    return CheckResult("sources.yaml", True, "parses OK")


def _check_continuity_config(root: Path) -> CheckResult:
    path = root / "config" / "continuity.yaml"
    if not path.is_file():
        return CheckResult("continuity.yaml", False, f"missing: {path}")
    try:
        load_continuity_config(path)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        return CheckResult("continuity.yaml", False, str(exc))
    return CheckResult("continuity.yaml", True, "parses OK")


def _check_signing_key(paths: BunkerPaths) -> CheckResult:
    priv = paths.data_root / "keys" / "signing.pem"
    pub = paths.data_root / "keys" / "signing.pub.pem"
    if not priv.is_file():
        return CheckResult("signing key", False, f"missing private key: {priv}")
    if not pub.is_file():
        return CheckResult("signing key", False, f"missing public key: {pub}")
    if sys.platform != "win32":
        mode = priv.stat().st_mode
        if mode & (stat.S_IRGRP | stat.S_IROTH | stat.S_IWGRP | stat.S_IWOTH):
            return CheckResult(
                "signing key",
                False,
                f"private key {priv} is group/world readable (expected 0600)",
            )
    return CheckResult("signing key", True, "present")


def _check_continuity_encryption(paths: ContinuityPaths, cfg: dict[str, Any]) -> CheckResult:
    inject_secrets_into_environ(("data_key",))
    require = bool(cfg.get("continuity", {}).get("require_encryption"))
    salt = paths.continuity_root / ".fernet_salt"
    has_key = encryption_available(paths.continuity_root) or salt.is_file()
    if require and not has_key:
        return CheckResult(
            "continuity encryption",
            False,
            "require_encryption set but no data key (keychain/env) and .fernet_salt missing",
        )
    if has_key:
        return CheckResult("continuity encryption", True, "key or salt configured")
    return CheckResult(
        "continuity encryption",
        True,
        "optional (no BUNKER_DATA_KEY — OK for loopback dev)",
    )


def _graph_credential_hint() -> bool:
    inject_secrets_into_environ()
    token = (get_secret("graph.access_token") or "").strip()
    if token:
        return True
    trio = (
        (get_secret("graph.tenant_id") or "").strip(),
        (get_secret("graph.client_id") or "").strip(),
        (get_secret("graph.client_secret") or "").strip(),
    )
    return all(trio)


def _check_graph_env() -> CheckResult:
    if _graph_credential_hint():
        return CheckResult("graph credentials", True, "token or app-only env vars present")
    return CheckResult(
        "graph credentials",
        False,
        "set BUNKER_GRAPH_ACCESS_TOKEN or BUNKER_GRAPH_TENANT_ID/CLIENT_ID/CLIENT_SECRET",
    )


def _check_graph_reachability() -> CheckResult:
    if not _graph_credential_hint():
        return CheckResult("graph reachability", True, "skipped (no credentials)")
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get("https://graph.microsoft.com/v1.0/$metadata")
    except (httpx.HTTPError, OSError) as exc:
        return CheckResult("graph reachability", False, str(exc))
    if resp.status_code in (401, 403):
        return CheckResult("graph reachability", True, "Microsoft Graph HTTP reachable")
    if resp.status_code < 500:
        return CheckResult("graph reachability", True, f"HTTP {resp.status_code}")
    return CheckResult("graph reachability", False, f"HTTP {resp.status_code}")


def probe_hosts_from_config(cfg: dict[str, Any]) -> list[dict[str, str]]:
    cont = cfg.get("continuity", {})
    watch = cont.get("watch") or {}
    hosts = watch.get("probe_hosts")
    if hosts is None:
        hosts = cont.get("probe_hosts")
    if not hosts:
        return []
    return list(hosts)


def _check_probe_hosts(cfg: dict[str, Any]) -> CheckResult:
    hosts = probe_hosts_from_config(cfg)
    if not hosts:
        return CheckResult(
            "watch probes",
            False,
            "no probe_hosts under continuity.watch in continuity.yaml",
        )
    return CheckResult("watch probes", True, f"{len(hosts)} probe(s) configured")


def run_doctor(root: Path | None = None) -> list[CheckResult]:
    root = root or Path.cwd()
    results: list[CheckResult] = []
    results.append(_check_sources_config(root))
    results.append(_check_continuity_config(root))
    try:
        cfg_src = load_sources_config(root / "config" / "sources.yaml")
        paths = BunkerPaths.from_config(root, cfg_src)
        results.append(_check_signing_key(paths))
    except Exception as exc:
        results.append(CheckResult("signing key", False, str(exc)))
    try:
        cfg_cont = load_continuity_config(root / "config" / "continuity.yaml")
        cpaths = ContinuityPaths.from_config(root, cfg_cont)
        results.append(_check_continuity_encryption(cpaths, cfg_cont))
        results.append(_check_probe_hosts(cfg_cont))
    except Exception as exc:
        results.append(CheckResult("continuity paths", False, str(exc)))
    results.append(_check_graph_env())
    results.append(_check_graph_reachability())
    return results