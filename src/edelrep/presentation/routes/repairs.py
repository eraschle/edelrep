from datetime import date as _date

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from edelrep.domain.exceptions import InvalidVehicleId, VehicleNotFound
from edelrep.domain.value_objects import VehicleId
from edelrep.presentation.dependencies import ContainerDep

router = APIRouter()


@router.get(
    "/vehicles/{registration_number}/repairs/new",
    response_class=HTMLResponse,
)
def new_repair_form(
    request: Request,
    container: ContainerDep,
    registration_number: str,
) -> HTMLResponse:
    try:
        vehicle_id = VehicleId(registration_number)
        if not container.vehicle_repo.exists(vehicle_id):
            raise VehicleNotFound(registration_number)
    except (VehicleNotFound, InvalidVehicleId) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "new_repair.html",
        {"registration_number": registration_number, "errors": {}},
    )


@router.post("/vehicles/{registration_number}/repairs", response_model=None)
def create_repair(
    request: Request,
    container: ContainerDep,
    registration_number: str,
    description: str = Form(...),
    date: str = Form(...),
) -> HTMLResponse | RedirectResponse:
    try:
        vehicle_id = VehicleId(registration_number)
    except InvalidVehicleId as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        parsed_date = _date.fromisoformat(date)
    except ValueError as exc:
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "new_repair.html",
            {
                "registration_number": registration_number,
                "errors": {"date": str(exc)},
            },
            status_code=400,
        )
    try:
        container.create_repair.execute(
            vehicle_id=vehicle_id,
            repair_date=parsed_date,
            description=description,
        )
    except VehicleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse(
        url=f"/vehicles/{registration_number}",
        status_code=303,
    )
