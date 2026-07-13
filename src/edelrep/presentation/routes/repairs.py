from datetime import date as _date

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from ulid import ULID

from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.exceptions import RepairNotFound, VehicleNotFound
from edelrep.presentation.container import Container
from edelrep.presentation.dependencies import ContainerDep
from edelrep.presentation.vehicle_lookup import resolve_vehicle, vehicle_url_key

router = APIRouter()


@router.get(
    "/vehicles/{vehicle_key}/repairs/new",
    response_class=HTMLResponse,
)
def new_repair_form(
    request: Request,
    container: ContainerDep,
    vehicle_key: str,
) -> HTMLResponse:
    try:
        vehicle = resolve_vehicle(container.vehicle_repo, vehicle_key)
    except VehicleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "new_repair.html",
        {"vehicle_key": vehicle_url_key(vehicle), "errors": {}},
    )


@router.post("/vehicles/{vehicle_key}/repairs", response_model=None)
def create_repair(
    request: Request,
    container: ContainerDep,
    vehicle_key: str,
    description: str = Form(""),
    date: str = Form(...),
) -> HTMLResponse | RedirectResponse | JSONResponse:
    wants_json = "application/json" in request.headers.get("accept", "")
    try:
        vehicle = resolve_vehicle(container.vehicle_repo, vehicle_key)
    except VehicleNotFound as exc:
        if wants_json:
            return JSONResponse({"error": str(exc)}, status_code=404)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    canonical_key = vehicle_url_key(vehicle)
    try:
        parsed_date = _date.fromisoformat(date)
    except ValueError as exc:
        if wants_json:
            return JSONResponse({"error": str(exc)}, status_code=400)
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "new_repair.html",
            {
                "vehicle_key": canonical_key,
                "errors": {"date": str(exc)},
            },
            status_code=400,
        )
    repair = container.create_repair.execute(
        vehicle_id=vehicle.id,
        repair_date=parsed_date,
        description=description.strip() or None,
    )
    if wants_json:
        return JSONResponse(
            {
                "repair_id": str(repair.id),
                "vehicle_url": f"/vehicles/{canonical_key}",
            },
            status_code=201,
        )
    return RedirectResponse(
        url=f"/vehicles/{canonical_key}",
        status_code=303,
    )


def _resolve_repair(
    container: Container, vehicle_key: str, repair_id: str
) -> tuple[Vehicle, Repair]:
    """Return (vehicle, repair) or raise HTTPException(404)."""
    try:
        vehicle = resolve_vehicle(container.vehicle_repo, vehicle_key)
    except VehicleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        rid = ULID.from_str(repair_id)
        repair = container.repair_repo.get(rid)
    except (ValueError, RepairNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if repair.vehicle_id != vehicle.id:
        raise HTTPException(status_code=404, detail="repair does not belong to vehicle")
    return vehicle, repair


@router.get(
    "/vehicles/{vehicle_key}/repairs/{repair_id}/edit",
    response_class=HTMLResponse,
)
def edit_repair_form(
    request: Request,
    container: ContainerDep,
    vehicle_key: str,
    repair_id: str,
) -> HTMLResponse:
    vehicle, repair = _resolve_repair(container, vehicle_key, repair_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "edit_repair.html",
        {
            "vehicle_key": vehicle_url_key(vehicle),
            "repair": repair,
            "form": {"description": repair.description or ""},
        },
    )


@router.post("/vehicles/{vehicle_key}/repairs/{repair_id}/edit", response_model=None)
def edit_repair(
    container: ContainerDep,
    vehicle_key: str,
    repair_id: str,
    description: str = Form(""),
) -> RedirectResponse:
    vehicle, repair = _resolve_repair(container, vehicle_key, repair_id)
    # The use case owns description normalization (strip, empty -> None).
    container.update_repair.execute(repair_id=repair.id, description=description)
    return RedirectResponse(url=f"/vehicles/{vehicle_url_key(vehicle)}", status_code=303)
