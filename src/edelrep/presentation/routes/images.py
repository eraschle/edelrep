from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from ulid import ULID

from edelrep.domain.exceptions import (
    DuplicateImage,
    ImageNotFound,
    RepairNotFound,
    VehicleNotFound,
)
from edelrep.presentation.dependencies import ContainerDep
from edelrep.presentation.vehicle_lookup import resolve_vehicle, vehicle_url_key

router = APIRouter()


class CommentPayload(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)


@router.get(
    "/vehicles/{vehicle_key}/repairs/{repair_id}/upload",
    response_class=HTMLResponse,
)
def upload_form(
    request: Request,
    container: ContainerDep,
    vehicle_key: str,
    repair_id: str,
) -> HTMLResponse:
    try:
        vehicle = resolve_vehicle(container.vehicle_repo, vehicle_key)
    except VehicleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "upload_image.html",
        {"vehicle_key": vehicle_url_key(vehicle), "repair_id": repair_id},
    )


@router.post(
    "/vehicles/{vehicle_key}/repairs/{repair_id}/images",
    response_model=None,
)
def upload_image(
    request: Request,
    container: ContainerDep,
    vehicle_key: str,
    repair_id: str,
    image: UploadFile,
    comment: str = Form(""),
) -> RedirectResponse | JSONResponse:
    wants_json = "application/json" in request.headers.get("accept", "")
    try:
        rid = ULID.from_str(repair_id)
    except ValueError as exc:
        if wants_json:
            return JSONResponse({"error": str(exc)}, status_code=404)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        vehicle = resolve_vehicle(container.vehicle_repo, vehicle_key)
    except VehicleNotFound as exc:
        if wants_json:
            return JSONResponse({"error": str(exc)}, status_code=404)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    canonical_key = vehicle_url_key(vehicle)
    raw = image.file.read()
    try:
        saved = container.upload_image.execute(
            repair_id=rid,
            raw_bytes=raw,
            filename=image.filename or "upload.jpg",
            comment=comment or None,
        )
    except RepairNotFound as exc:
        if wants_json:
            return JSONResponse({"error": str(exc)}, status_code=404)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DuplicateImage as exc:
        if wants_json:
            return JSONResponse({"error": str(exc)}, status_code=422)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        if wants_json:
            return JSONResponse({"error": str(exc)}, status_code=422)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if wants_json:
        return JSONResponse({"image_id": str(saved.id)}, status_code=201)
    return RedirectResponse(
        url=f"/vehicles/{canonical_key}",
        status_code=303,
    )


@router.patch("/images/{image_id}/comment")
def patch_image_comment(
    container: ContainerDep,
    image_id: str,
    payload: CommentPayload,
) -> JSONResponse:
    try:
        iid = ULID.from_str(image_id)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    try:
        updated = container.update_image_comment.execute(iid, payload.comment)
    except ImageNotFound as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse({"image_id": str(updated.id), "comment": updated.comment})


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
