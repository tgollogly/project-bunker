from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.schedule import ScheduleSpec, install_schedule
from bunker.continuity.serve.auth import save_password_hash
from bunker.continuity.setup.state import SetupState, load_setup_state, save_setup_state
from bunker.secrets.store import set_secret


def register_setup_routes(
    app: FastAPI,
    paths: ContinuityPaths,
    templates: Any,
    render: Callable[..., HTMLResponse],
) -> None:
    continuity_root = paths.continuity_root
    auth_path = continuity_root / "serve_auth.json"

    @app.get("/setup", response_class=HTMLResponse)
    def setup_wizard(request: Request) -> HTMLResponse:
        state = load_setup_state(continuity_root)
        return render(
            "setup.html",
            request,
            "setup",
            {
                "state": state,
                "completed": state.completed,
            },
        )

    @app.post("/setup")
    def setup_submit(
        request: Request,
        sources: str = Form(""),
        interval_hours: int = Form(6),
        data_passphrase: str = Form(""),
        serve_password: str = Form(""),
        graph_tenant: str = Form(""),
        graph_client_id: str = Form(""),
        graph_client_secret: str = Form(""),
        google_client_id: str = Form(""),
        google_refresh_token: str = Form(""),
        ical_urls: str = Form(""),
        contacts_paths: str = Form(""),
        local_folder: str = Form(""),
    ) -> RedirectResponse:
        selected = [s.strip() for s in sources.replace(",", " ").split() if s.strip()]
        state = SetupState(
            completed=True,
            selected_sources=selected,
            sync_interval_hours=interval_hours,
            encryption_passphrase_set=bool(data_passphrase),
        )
        if data_passphrase:
            set_secret("data_key", data_passphrase)
        if graph_tenant:
            set_secret("graph.tenant_id", graph_tenant)
        if graph_client_id:
            set_secret("graph.client_id", graph_client_id)
        if graph_client_secret:
            set_secret("graph.client_secret", graph_client_secret)
        if google_client_id:
            set_secret("google.client_id", google_client_id)
        if google_refresh_token:
            set_secret("google.refresh_token", google_refresh_token)
        if serve_password:
            save_password_hash(auth_path, serve_password)
        _write_sync_sources_config(
            paths,
            sources=selected,
            ical_urls=ical_urls,
            contacts_paths=contacts_paths,
            local_folder=local_folder,
        )
        save_setup_state(continuity_root, state)
        try:
            install_schedule(ScheduleSpec(interval_hours=interval_hours))
        except Exception:
            pass
        return RedirectResponse(url="/", status_code=303)


def _write_sync_sources_config(
    paths: ContinuityPaths,
    *,
    sources: list[str],
    ical_urls: str,
    contacts_paths: str,
    local_folder: str,
) -> None:
    """Merge wizard choices into config/continuity.yaml sync_sources (best effort)."""
    import yaml

    root = paths.root
    cfg_path = root / "config" / "continuity.yaml"
    if not cfg_path.is_file():
        return
    with cfg_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    cont = data.setdefault("continuity", {})
    entries: list[dict[str, Any]] = []
    if "microsoft_graph" in sources:
        entries.append({"id": "m365", "type": "microsoft_graph", "enabled": True})
    if "google_workspace" in sources:
        entries.append({"id": "google", "type": "google_workspace", "enabled": True})
    if "ical" in sources and ical_urls.strip():
        urls = [u.strip() for u in ical_urls.splitlines() if u.strip()]
        entries.append({"id": "ical", "type": "ical", "enabled": True, "urls": urls})
    if "contacts_file" in sources and contacts_paths.strip():
        paths_csv = [p.strip() for p in contacts_paths.splitlines() if p.strip()]
        entries.append(
            {"id": "contacts_file", "type": "contacts_file", "enabled": True, "paths": paths_csv}
        )
    if "local_folder" in sources and local_folder.strip():
        entries.append(
            {
                "id": "local_runbooks",
                "type": "local_folder",
                "enabled": True,
                "path": local_folder.strip(),
                "docs_id": "local_runbooks",
            }
        )
    cont["sync_sources"] = entries
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")