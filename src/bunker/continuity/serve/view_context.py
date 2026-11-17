from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from bunker import __version__
from bunker.continuity.aggregate import query_all_calendar_rows, query_all_contact_rows
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.status import continuity_status
from bunker.continuity.storage import iter_encrypted_doc_files, read_encrypted_file
from bunker.continuity.watch.health import HealthState, WatchState, load_watch_state

_LONDON = ZoneInfo("Europe/London")

_BANNER = {
    HealthState.OK: (
        "status-banner--ok",
        "Cloud services look reachable",
    ),
    HealthState.DEGRADED: (
        "status-banner--degraded",
        "Cloud services may be degraded",
    ),
    HealthState.DOWN: (
        "status-banner--down",
        "Cloud appears DOWN — use your offline copy",
    ),
}


@dataclass
class MeetingCard:
    time_label: str
    subject: str
    location: str


@dataclass
class ContactCard:
    name: str
    role: str
    email: str
    mobile: str


@dataclass
class RunbookLink:
    title: str
    description: str
    href: str


RUNBOOK_CATALOG: dict[str, tuple[str, str]] = {
    "outage-checklist.md": (
        "Outage checklist",
        "Offline steps when Microsoft 365 is unreachable (sample).",
    ),
}


def _incident_short_label(incident_id: str | None) -> tuple[str | None, str | None]:
    if not incident_id:
        return None, None
    suffix = incident_id.split("-")[-1] if "-" in incident_id else incident_id[-8:]
    short = suffix[-8:] if len(suffix) > 8 else suffix
    return f"Incident #{short}", incident_id


@dataclass
class FreshnessRow:
    source_id: str
    ago_label: str
    stale: bool


@dataclass
class ProbeRow:
    name: str
    up: bool


def _format_london(ts: float) -> str:
    if ts <= 0:
        return "unknown"
    dt = datetime.fromtimestamp(ts, tz=ZoneInfo("UTC")).astimezone(_LONDON)
    return dt.strftime("%H:%M, %d %b")


def _ago(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} seconds ago"
    if seconds < 3600:
        m = seconds // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if seconds < 86400:
        h = seconds // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = seconds // 86400
    return f"{d} day{'s' if d != 1 else ''} ago"


def latest_incident_id(incidents_root: Path) -> str | None:
    if not incidents_root.is_dir():
        return None
    files = sorted(incidents_root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    try:
        doc = json.loads(files[0].read_text(encoding="utf-8"))
        return str(doc.get("id") or files[0].stem)
    except (json.JSONDecodeError, OSError):
        return files[0].stem


def has_sample_data(paths: ContinuityPaths) -> bool:
    for row in continuity_status(paths):
        details = row.get("details") or {}
        if details.get("sample"):
            return True
    return False


def probe_rows(watch: WatchState) -> list[ProbeRow]:
    out: list[ProbeRow] = []
    for name, ok in sorted((watch.probes or {}).items()):
        out.append(ProbeRow(name=name.replace("_", " ").title(), up=bool(ok)))
    return out


def watch_banner(watch: WatchState, incident_id: str | None) -> dict[str, str]:
    cls, headline = _BANNER[watch.state]
    since = _format_london(watch.updated_at)
    incident_label, incident_full = _incident_short_label(incident_id)
    role = "alert" if watch.state == HealthState.DOWN else "status"
    return {
        "banner_class": cls,
        "headline": headline,
        "since_line": since,
        "incident_label": incident_label or "",
        "incident_full": incident_full or "",
        "banner_role": role,
    }


def base_page_context(
    paths: ContinuityPaths,
    *,
    active_nav: str,
    element_url: str | None,
) -> dict[str, Any]:
    watch = load_watch_state(paths.state_file)
    incident_id = latest_incident_id(paths.incidents_root)
    banner = watch_banner(watch, incident_id)
    return {
        "active_nav": active_nav,
        "element_url": element_url,
        "watch_state": watch.state.value,
        "sample_data": has_sample_data(paths),
        "probes": probe_rows(watch),
        "latest_incident_id": incident_id or "",
        "bunker_version": __version__,
        **banner,
    }


def load_meetings(paths: ContinuityPaths, *, limit: int = 5) -> list[MeetingCard]:
    raw = query_all_calendar_rows(
        paths,
        columns=["subject", "start", "end", "location"],
        limit=100,
    )
    cards: list[MeetingCard] = []
    for subj, start, _end, loc in raw[:limit]:
        time_label = _short_time(str(start or ""))
        cards.append(
            MeetingCard(
                time_label=time_label,
                subject=str(subj or ""),
                location=str(loc or "") or "—",
            )
        )
    return cards


def _short_time(iso: str) -> str:
    if not iso:
        return "—"
    try:
        if "T" in iso:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            return dt.astimezone(_LONDON).strftime("%H:%M")
        return iso[:16]
    except ValueError:
        return iso[:16]


def load_contacts(paths: ContinuityPaths, *, q: str = "", limit: int = 200) -> list[ContactCard]:
    raw = query_all_contact_rows(
        paths,
        columns=["display_name", "email", "mobile", "company"],
        limit=limit,
    )
    needle = q.strip().lower()
    rows: list[ContactCard] = []
    for tup in raw:
        if len(tup) < 3:
            continue
        name, email, mobile = tup[0], tup[1], tup[2]
        company = tup[3] if len(tup) > 3 else ""
        name_s = str(name or "")
        if needle and needle not in name_s.lower() and needle not in str(email or "").lower():
            continue
        rows.append(
            ContactCard(
                name=name_s,
                role=str(company or "") or "—",
                email=str(email or ""),
                mobile=str(mobile or ""),
            )
        )
    return rows


def load_runbook_links(paths: ContinuityPaths) -> list[RunbookLink]:
    from urllib.parse import quote

    links: list[RunbookLink] = []
    for f in iter_encrypted_doc_files(paths.docs_root):
        rel = f.relative_to(paths.docs_root).as_posix()
        file_name = rel.replace(".md.enc", "").replace(".enc", "").rsplit("/", 1)[-1]
        title, desc = RUNBOOK_CATALOG.get(file_name, (file_name.replace("-", " ").title(), ""))
        links.append(
            RunbookLink(
                title=title,
                description=desc,
                href=f"/runbooks/view?path={quote(rel, safe='/')}",
            )
        )
    return sorted(links, key=lambda x: x.title.lower())


def freshness_rows(paths: ContinuityPaths) -> list[FreshnessRow]:
    out: list[FreshnessRow] = []
    for row in continuity_status(paths):
        out.append(
            FreshnessRow(
                source_id=row["source_id"],
                ago_label=f"updated {_ago(int(row.get('age_seconds', 0)))}",
                stale=bool(row.get("stale")),
            )
        )
    return out


def sync_table_rows(paths: ContinuityPaths) -> list[dict[str, Any]]:
    return continuity_status(paths)


def runbook_plaintext(paths: ContinuityPaths, rel_path: str) -> tuple[str, str]:
    """Return (title, text) for a runbook under docs_root."""
    target = (paths.docs_root / rel_path).resolve()
    if not str(target).startswith(str(paths.docs_root.resolve())):
        raise ValueError("invalid path")
    enc = target if target.name.endswith(".enc") else target.with_suffix(target.suffix + ".enc")
    if not enc.is_file():
        raise FileNotFoundError(rel_path)
    body = read_encrypted_file(enc, continuity_root=paths.continuity_root)
    title = enc.name.replace(".md.enc", "").replace(".enc", "")
    return title, body.decode("utf-8", errors="replace")