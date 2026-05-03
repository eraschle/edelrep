from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from ulid import ULID

from edelrep.domain.exceptions import (
    ImageNotFound,
    InvalidVehicleId,
    RepairNotFound,
    VehicleNotFound,
)
from edelrep.domain.value_objects import VehicleId
from edelrep.presentation.dependencies import ContainerDep

router = APIRouter()


@router.get(
    "/vehicles/{registration_number}/repairs/{repair_id}/upload",
    response_class=HTMLResponse,
)
def upload_form(
    request: Request,
    container: ContainerDep,
    registration_number: str,
    repair_id: str,
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
        "upload_image.html",
        {"registration_number": registration_number, "repair_id": repair_id},
    )


@router.post(
    "/vehicles/{registration_number}/repairs/{repair_id}/images",
    response_model=None,
)
def upload_image(
    container: ContainerDep,
    registration_number: str,
    repair_id: str,
    image: UploadFile,
) -> RedirectResponse:
    try:
        rid = ULID.from_str(repair_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raw = image.file.read()
    try:
        container.upload_image.execute(
            repair_id=rid,
            raw_bytes=raw,
            filename=image.filename or "upload.jpg",
        )
    except RepairNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RedirectResponse(
        url=f"/vehicles/{registration_number}",
        status_code=303,
    )


@router.get("/images/{image_id}/raw")
def get_raw_image(
    container: ContainerDep,
    image_id: str,
) -> Response:
    try:
        iid = ULID.from_str(image_id)
        img, raw = container.get_image.execute(iid)
    except (ValueError, ImageNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=raw, media_type=img.mime_type)


@router.get("/images/{image_id}/thumbnail")
def get_thumbnail(
    container: ContainerDep,
    image_id: str,
) -> Response:
    try:
        iid = ULID.from_str(image_id)
        img = container.image_repo.get(iid)
    except (ValueError, ImageNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if img.thumbnail_key is None:
        raise HTTPException(status_code=404, detail="No thumbnail")
    raw = container.backend.read_bytes(img.thumbnail_key)
    return Response(content=raw, media_type=img.mime_type)
