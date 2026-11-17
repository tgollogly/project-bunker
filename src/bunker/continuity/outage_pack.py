"""Generate a printable PDF outage pack after each sync."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fpdf import FPDF

from bunker.continuity.aggregate import query_all_calendar_rows, query_all_contact_rows
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.serve.view_context import load_runbook_links
from bunker.io.atomic import atomic_write_bytes

logger = logging.getLogger(__name__)

_LONDON = ZoneInfo("Europe/London")
_DISCLAIMER = (
    "Project Bunker - independent open-source software (MIT). "
    "Not affiliated with Microsoft, Google, or any cloud provider. "
    "Trademarks belong to their owners."
)


def _pdf_text(value: str) -> str:
    return value.encode("latin-1", errors="replace").decode("latin-1")


def _in_next_days(iso: str, *, days: int = 7) -> bool:
    if not iso:
        return False
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    now = datetime.now(timezone.utc)
    return now <= dt <= now + timedelta(days=days)


def generate_outage_pack_pdf(paths: ContinuityPaths, *, days: int = 7) -> Path:
    paths.ensure()
    out = paths.continuity_root / "outage_pack.pdf"
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    line_w = pdf.epw
    pdf.set_font("Helvetica", size=14)
    pdf.cell(0, 10, _pdf_text("Bunker Continuity - Outage pack"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    pdf.multi_cell(line_w, 5, _pdf_text(_DISCLAIMER))
    pdf.ln(4)
    generated = datetime.now(_LONDON).strftime("%Y-%m-%d %H:%M %Z")
    pdf.cell(0, 6, f"Generated: {generated}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", style="B", size=11)
    pdf.cell(0, 8, _pdf_text(f"Calendar - next {days} days"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    cal = query_all_calendar_rows(
        paths,
        columns=["subject", "start", "end", "location"],
        limit=200,
    )
    shown = 0
    for subj, start, end, loc in cal:
        if not _in_next_days(str(start or ""), days=days):
            continue
        line = _pdf_text(f"- {subj} ({start} - {end}) @ {loc or '-'}")
        pdf.multi_cell(line_w, 5, line[:240])
        shown += 1
    if shown == 0:
        pdf.cell(0, 6, "(no events in range)", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("Helvetica", style="B", size=11)
    pdf.cell(0, 8, "Key contacts", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    contacts = query_all_contact_rows(
        paths,
        columns=["display_name", "email", "mobile", "company"],
        limit=50,
    )
    for row in contacts[:25]:
        name, email, mobile, company = (row + ("", "", "", ""))[:4]
        pdf.multi_cell(
            line_w, 5, _pdf_text(f"- {name} - {email} - {mobile} ({company or '-'})")[:240]
        )

    pdf.ln(3)
    pdf.set_font("Helvetica", style="B", size=11)
    pdf.cell(0, 8, "Documents", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    for link in load_runbook_links(paths)[:30]:
        pdf.multi_cell(line_w, 5, _pdf_text(f"- {link.title}: {link.description}")[:240])

    raw = pdf.output()
    data = bytes(raw) if isinstance(raw, (bytes, bytearray)) else raw.encode("latin-1")
    atomic_write_bytes(out, data)
    logger.info("Wrote outage pack PDF to %s", out)
    return out


def outage_pack_status(paths: ContinuityPaths) -> dict[str, Any]:
    out = paths.continuity_root / "outage_pack.pdf"
    if not out.is_file():
        return {"present": False}
    st = out.stat()
    return {
        "present": True,
        "path": str(out),
        "size_bytes": st.st_size,
        "mtime": st.st_mtime,
    }