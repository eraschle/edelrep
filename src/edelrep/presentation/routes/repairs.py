from datetime import date as _date

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from edelrep.domain.exceptions import VehicleNotFound
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
