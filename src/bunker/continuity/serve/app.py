from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from bunker.continuity.parquet_io import query_rows_from_root
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.seed_sample import SAMPLE_CONTACT_NAME
from bunker.continuity.serve.auth import ServeAuthConfig, serve_auth_middleware
from bunker.continuity.serve.security import SECURITY_HEADERS, safe_element_url
from bunker.continuity.status import continuity_status
from bunker.continuity.storage import iter_encrypted_doc_files
from bunker.continuity.watch.health import load_watch_state

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


@dataclass
class CalendarRow:
    subject: str
    start: str
    end: str


@dataclass
class ContactRow:
    name: str
    email: str
    mobile: str


def create_app(
    paths: ContinuityPaths,
    cfg: dict[str, Any],
    *,
    bind_host: str = "127.0.0.1",
    auth: ServeAuthConfig | None = None,
) -> FastAPI:
    app = FastAPI(title="Bunker Continuity", docs_url=None, redoc_url=None)
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

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        watch = load_watch_state(paths.state_file)
        featured_contact = None
        names = query_rows_from_root(
            paths.parquet_root / "m365" / "contacts",
            ["display_name"],
            order_by="display_name",
            limit=50,
            continuity_root=continuity_root,
        )
        for (name,) in names:
            if str(name or "") == SAMPLE_CONTACT_NAME:
                featured_contact = SAMPLE_CONTACT_NAME
                break
        if featured_contact is None and names:
            featured_contact = str(names[0][0] or "")
        return templates.TemplateResponse(
            request,
            "home.html",
            {
                "watch_state": watch.state.value,
                "element_url": element_url,
                "featured_contact": featured_contact,
            },
        )

    @app.get("/status", response_class=HTMLResponse)
    def status_page(request: Request) -> HTMLResponse:
        rows = continuity_status(paths)
        watch = load_watch_state(paths.state_file)
        return templates.TemplateResponse(
            request,
            "status.html",
            {
                "watch_state": watch.state.value,
                "rows": rows,
            },
        )

    @app.get("/calendar", response_class=HTMLResponse)
    def calendar_page(request: Request) -> HTMLResponse:
        raw_rows = query_rows_from_root(
            paths.parquet_root / "m365" / "calendar",
            ["subject", "start", "end"],
            order_by="start",
            limit=100,
            continuity_root=continuity_root,
        )
        rows = [
            CalendarRow(subject=str(s or ""), start=str(st or ""), end=str(en or ""))
            for s, st, en in raw_rows
        ]
        return templates.TemplateResponse(request, "calendar.html", {"rows": rows})

    @app.get("/contacts", response_class=HTMLResponse)
    def contacts_page(request: Request) -> HTMLResponse:
        raw_rows = query_rows_from_root(
            paths.parquet_root / "m365" / "contacts",
            ["display_name", "email", "mobile"],
            order_by="display_name",
            limit=200,
            continuity_root=continuity_root,
        )
        rows = [
            ContactRow(name=str(n or ""), email=str(e or ""), mobile=str(m or ""))
            for n, e, m in raw_rows
        ]
        return templates.TemplateResponse(request, "contacts.html", {"rows": rows})

    @app.get("/docs", response_class=HTMLResponse)
    def docs_page(request: Request) -> HTMLResponse:
        items: list[str] = []
        for f in iter_encrypted_doc_files(paths.docs_root):
            rel = f.relative_to(paths.continuity_root).as_posix()
            items.append(f"{rel} ({f.stat().st_size} bytes encrypted)")
        return templates.TemplateResponse(request, "docs.html", {"items": items})

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
            }
        )

    return app