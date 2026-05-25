"""Update check + apply endpoints.

The "apply" route exits the server process; a watchdog (the start_edelrep
batch script's restart loop) is expected to ``git pull`` and relaunch.
"""

from __future__ import annotations

import os
import threading

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from edelrep.presentation.dependencies import ContainerDep

router = APIRouter()

_SHUTDOWN_DELAY_SECONDS = 0.5


@router.get("/admin/updates", response_class=HTMLResponse)
def updates_page(request: Request, container: ContainerDep) -> HTMLResponse:
    status = container.update_checker.status()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "admin_updates.html",
        {"status": status},
    )


@router.get("/admin/updates/status")
def updates_status(container: ContainerDep) -> JSONResponse:
    status = container.update_checker.status()
    return JSONResponse(
        {
            "current": status.current,
            "current_short": status.current_short,
            "latest": status.latest,
            "latest_short": status.latest_short,
            "update_available": status.update_available,
        }
    )


@router.post("/admin/updates/apply")
def updates_apply() -> JSONResponse:
    """Exit the process; the watchdog batch loop restarts with `git pull`."""
    threading.Timer(_SHUTDOWN_DELAY_SECONDS, lambda: os._exit(0)).start()
    return JSONResponse({"status": "restarting"}, status_code=202)
