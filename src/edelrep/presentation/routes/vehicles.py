from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from edelrep.domain.exceptions import (
    DuplicateVehicle,
    InvalidVehicleId,
    VehicleNotFound,
)
from edelrep.domain.value_objects import VehicleId
from edelrep.presentation.dependencies import ContainerDep
from edelrep.presentation.labels import REPAIR_FIELDS, VEHICLE_FIELDS

router = APIRouter()


@router.get("/vehicles/new", response_class=HTMLResponse)
def new_vehicle_form(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "new_vehicle.html", {"errors": {}})


@router.post("/vehicles", response_model=None)
def create_vehicle(
    request: Request,
    container: ContainerDep,
    registration_number: str = Form(...),
    vin: str = Form(""),
    description: str = Form(""),
) -> HTMLResponse | RedirectResponse:
    try:
        vehicle = container.create_vehicle.execute(
            registration_number=registration_number,
            vin=vin or None,
            description=description or None,
        )
    except (InvalidVehicleId, DuplicateVehicle) as exc:
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "new_vehicle.html",
            {"errors": {"registration_number": str(exc)}},
            status_code=400,
        )
    return RedirectResponse(
        url=f"/vehicles/{vehicle.id.registration_number}",
        status_code=303,
    )


@router.get("/vehicles/{registration_number}", response_class=HTMLResponse)
def vehicle_detail(
    request: Request,
    container: ContainerDep,
    registration_number: str,
) -> HTMLResponse:
    try:
        vehicle_id = VehicleId(registration_number)
        vehicle = container.vehicle_repo.get(vehicle_id)
    except (VehicleNotFound, InvalidVehicleId) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    repairs = list(container.list_repairs.execute(vehicle.id))
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "vehicle_detail.html",
        {
            "vehicle": vehicle,
            "repairs": repairs,
            "vehicle_labels": VEHICLE_FIELDS,
            "repair_labels": REPAIR_FIELDS,
        },
    )
