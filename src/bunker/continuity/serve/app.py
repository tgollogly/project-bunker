from __future__ import annotations

from typing import Any

import duckdb
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.status import continuity_status
from bunker.continuity.watch.health import load_watch_state


def create_app(paths: ContinuityPaths, cfg: dict[str, Any]) -> FastAPI:
    app = FastAPI(title="Bunker Continuity", docs_url=None, redoc_url=None)
    element_url = cfg.get("continuity", {}).get("element_url", "/")

    def _page(body: str) -> str:
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Bunker Continuity</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;line-height:1.5}}
nav a{{margin-right:1rem}}
table{{border-collapse:collapse}}
td,th{{border:1px solid #ccc;padding:.4rem}}
.stale{{color:#a00}}</style></head>
<body><nav><a href="/">Home</a><a href="/calendar">Calendar</a>
<a href="/contacts">Contacts</a><a href="/docs">Docs</a><a href="/status">Status</a></nav>
{body}</body></html>"""

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        watch = load_watch_state(paths.state_file)
        return _page(
            f"<h1>Bunker Continuity</h1><p>M365 watch: <strong>{watch.state.value}</strong></p>"
            f'<p><a href="{element_url}">Open backup chat (Element)</a></p>'
            "<p>All assets are loaded locally — no CDN.</p>"
        )

    @app.get("/status", response_class=HTMLResponse)
    def status_page() -> str:
        rows = continuity_status(paths)
        watch = load_watch_state(paths.state_file)
        header = (
            "<h1>Sync status</h1>"
            f"<p>Watch: {watch.state.value}</p>"
            "<table><tr><th>Source</th><th>Last OK</th><th>Age (s)</th></tr>"
        )
        lines = [header]
        for r in rows:
            cls = ' class="stale"' if r.get("stale") else ""
            lines.append(
                f"<tr{cls}><td>{r['source_id']}</td><td>{r.get('last_success_iso')}</td>"
                f"<td>{r.get('age_seconds')}</td></tr>"
            )
        lines.append("</table>")
        return _page("".join(lines))

    @app.get("/calendar", response_class=HTMLResponse)
    def calendar_page() -> str:
        glob = str(paths.parquet_root / "m365" / "calendar" / "**" / "*.parquet")
        con = duckdb.connect(":memory:")
        try:
            rows = con.execute(
                "SELECT subject, start, end, location FROM read_parquet(?, union_by_name=true) "
                "ORDER BY start LIMIT 100",
                [glob],
            ).fetchall()
        except Exception:
            rows = []
        finally:
            con.close()
        body = (
            "<h1>Calendar (local cache)</h1>"
            "<table><tr><th>Subject</th><th>Start</th><th>End</th></tr>"
        )
        for subj, start, end, _loc in rows:
            body += f"<tr><td>{subj}</td><td>{start}</td><td>{end}</td></tr>"
        body += "</table>"
        return _page(body)

    @app.get("/contacts", response_class=HTMLResponse)
    def contacts_page() -> str:
        glob = str(paths.parquet_root / "m365" / "contacts" / "**" / "*.parquet")
        con = duckdb.connect(":memory:")
        try:
            rows = con.execute(
                "SELECT display_name, email, mobile FROM read_parquet(?, union_by_name=true) "
                "ORDER BY display_name LIMIT 200",
                [glob],
            ).fetchall()
        except Exception:
            rows = []
        finally:
            con.close()
        body = "<h1>Contacts</h1><table><tr><th>Name</th><th>Email</th><th>Mobile</th></tr>"
        for name, email, mobile in rows:
            body += f"<tr><td>{name}</td><td>{email}</td><td>{mobile}</td></tr>"
        body += "</table>"
        return _page(body)

    @app.get("/docs", response_class=HTMLResponse)
    def docs_page() -> str:
        items: list[str] = ["<h1>Runbook documents</h1><ul>"]
        if paths.docs_root.is_dir():
            for f in sorted(paths.docs_root.rglob("*")):
                if f.is_file():
                    rel = f.relative_to(paths.continuity_root)
                    items.append(f"<li>{rel.as_posix()} ({f.stat().st_size} bytes)</li>")
        items.append("</ul>")
        return _page("".join(items))

    @app.get("/api/status")
    def api_status() -> JSONResponse:
        watch = load_watch_state(paths.state_file)
        return JSONResponse(
            {
                "watch": watch.state.value,
                "sync": continuity_status(paths),
            }
        )

    return app