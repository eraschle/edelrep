from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from edelrep.domain.exceptions import (
    DuplicateRegistrationNumber,
    DuplicateVin,
    InvalidRegistrationNumber,
    InvalidVin,
    VehicleIdentifierRequired,
    VehicleNotFound,
)
from edelrep.presentation.dependencies import ContainerDep
from edelrep.presentation.labels import REPAIR_FIELDS, VEHICLE_FIELDS
from edelrep.presentation.vehicle_lookup import resolve_vehicle, vehicle_url

router = APIRouter()


@router.get("/vehicles/new", response_class=HTMLResponse)
def new_vehicle_form(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "new_vehicle.html",
        {"errors": {}, "form": {}},
    )


@router.post("/vehicles", response_model=None)
def create_vehicle(
    request: Request,
    container: ContainerDep,
    registration_number: str = Form(""),
    vin: str = Form(""),
    description: str = Form(""),
) -> HTMLResponse | RedirectResponse:
    form_values = {
        "registration_number": registration_number,
        "vin": vin,
        "description": description,
    }
    try:
        vehicle = container.create_vehicle.execute(
            registration_number=registration_number or None,
            vin=vin or None,
            description=description or None,
        )
    except VehicleIdentifierRequired as exc:
        return _form_error(request, form_values, {"identifier": str(exc)})
    except InvalidRegistrationNumber as exc:
        return _form_error(request, form_values, {"registration_number": str(exc)})
    except InvalidVin as exc:
        return _form_error(request, form_values, {"vin": str(exc)})
    except DuplicateRegistrationNumber as exc:
        return _form_error(request, form_values, {"registration_number": str(exc)})
    except DuplicateVin as exc:
        return _form_error(request, form_values, {"vin": str(exc)})
    return RedirectResponse(url=vehicle_url(vehicle), status_code=303)


@router.get("/vehicles/{vehicle_key}", response_class=HTMLResponse)
def vehicle_detail(
    request: Request,
    container: ContainerDep,
    vehicle_key: str,
) -> HTMLResponse:
    try:
        vehicle = resolve_vehicle(container.vehicle_repo, vehicle_key)
    except VehicleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    repairs = list(container.list_repairs.execute(vehicle.id))
    images_by_repair = {str(r.id): list(container.image_repo.list_for_repair(r.id)) for r in repairs}
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "vehicle_detail.html",
        {
            "vehicle": vehicle,
            "vehicle_key": vehicle_key,
            "repairs": repairs,
            "vehicle_labels": VEHICLE_FIELDS,
            "repair_labels": REPAIR_FIELDS,
            "images_by_repair": images_by_repair,
        },
    )


def _form_error(
    request: Request,
    form_values: dict[str, str],
    errors: dict[str, str],
) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "new_vehicle.html",
        {"errors": errors, "form": form_values},
        status_code=400,
    )
