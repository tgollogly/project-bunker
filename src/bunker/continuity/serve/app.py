from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from bunker.continuity.aggregate import query_all_calendar_rows
from bunker.continuity.outage_pack import outage_pack_status
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.serve.auth import ServeAuthConfig, serve_auth_middleware
from bunker.continuity.serve.security import SECURITY_HEADERS, safe_element_url
from bunker.continuity.serve.setup_routes import register_setup_routes
from bunker.continuity.serve.view_context import (
    base_page_context,
    freshness_rows,
    load_contacts,
    load_meetings,
    load_runbook_links,
    runbook_plaintext,
    sync_table_rows,
)
from bunker.continuity.setup.state import load_setup_state
from bunker.continuity.status import continuity_status
from bunker.continuity.watch.health import load_watch_state

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_STATIC_DIR = Path(__file__).resolve().parent / "static"


@dataclass
class CalendarRow:
    subject: str
    start: str
    end: str
    location: str


def create_app(
    paths: ContinuityPaths,
    cfg: dict[str, Any],
    *,
    bind_host: str = "127.0.0.1",
    auth: ServeAuthConfig | None = None,
) -> FastAPI:
    app = FastAPI(title="Bunker Continuity", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
    templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))
    templates.env.autoescape = True
    element_url = safe_element_url(cfg.get("continuity", {}).get("element_url"))
    continuity_root = paths.continuity_root

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers[key] = value
        return response

    if auth is not None:
        app.middleware("http")(serve_auth_middleware(auth, bind_host))

    def _render(
        name: str,
        request: Request,
        active_nav: str,
        extra: dict[str, Any],
    ) -> HTMLResponse:
        ctx = {
            **base_page_context(paths, active_nav=active_nav, element_url=element_url),
            **extra,
        }
        return templates.TemplateResponse(request, name, ctx)

    register_setup_routes(app, paths, templates, _render)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return _render(
            "home.html",
            request,
            "home",
            {
                "meetings": load_meetings(paths, limit=5),
                "contacts": load_contacts(paths, limit=6),
                "runbooks": load_runbook_links(paths),
                "freshness": freshness_rows(paths),
            },
        )

    @app.get("/status", response_class=HTMLResponse)
    def status_page(request: Request) -> HTMLResponse:
        return _render(
            "status.html",
            request,
            "status",
            {"sync_rows": sync_table_rows(paths)},
        )

    @app.get("/calendar", response_class=HTMLResponse)
    def calendar_page(request: Request) -> HTMLResponse:
        raw_rows = query_all_calendar_rows(
            paths,
            columns=["subject", "start", "end", "location"],
            limit=100,
        )
        rows = [
            CalendarRow(
                subject=str(s or ""),
                start=str(st or ""),
                end=str(en or ""),
                location=str(loc or "") or "—",
            )
            for s, st, en, loc in raw_rows
        ]
        return _render("calendar.html", request, "calendar", {"rows": rows})

    @app.get("/contacts", response_class=HTMLResponse)
    def contacts_page(request: Request, q: str = "") -> HTMLResponse:
        rows = load_contacts(paths, q=q)
        return _render(
            "contacts.html",
            request,
            "contacts",
            {"rows": rows, "search_q": q},
        )

    @app.get("/runbooks", response_class=HTMLResponse)
    def runbooks_page(request: Request) -> HTMLResponse:
        return _render(
            "runbooks.html",
            request,
            "runbooks",
            {"runbooks": load_runbook_links(paths)},
        )

    @app.get("/runbooks/view", response_class=HTMLResponse)
    def runbook_view(request: Request, path: str) -> HTMLResponse:
        try:
            title, body = runbook_plaintext(paths, path)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _render(
            "runbook_view.html",
            request,
            "runbooks",
            {"doc_title": title, "doc_body": body},
        )

    @app.get("/docs", response_class=RedirectResponse)
    def docs_redirect() -> RedirectResponse:
        return RedirectResponse(url="/runbooks", status_code=302)

    @app.get("/outage-pack.pdf")
    def outage_pack_download() -> FileResponse:
        pack = paths.continuity_root / "outage_pack.pdf"
        if not pack.is_file():
            raise HTTPException(status_code=404, detail="outage pack not generated yet")
        return FileResponse(pack, media_type="application/pdf", filename="outage_pack.pdf")

    if auth is not None:

        @app.post("/login")
        def login(  # noqa: B008
            request: Request,
            password: str = Form(...),
        ) -> Response:
            client_ip = request.client.host if request.client else "unknown"
            if not auth.check_login_allowed(client_ip):
                return JSONResponse({"detail": "too many attempts"}, status_code=429)
            if not auth.verify_login(password):
                auth.record_failed_login(client_ip)
                return JSONResponse({"detail": "invalid credentials"}, status_code=401)
            response = RedirectResponse(url="/", status_code=303)
            auth.issue_session(response)
            return response

    @app.get("/api/status")
    def api_status() -> JSONResponse:
        watch = load_watch_state(paths.state_file)
        return JSONResponse(
            {
                "watch": watch.state.value,
                "sync": continuity_status(paths),
                "setup": load_setup_state(continuity_root).__dict__,
                "outage_pack": outage_pack_status(paths),
            }
        )

    return app