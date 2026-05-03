import mimetypes

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from edelrep.presentation.dependencies import ContainerDep

router = APIRouter()

_INBOX_PREFIX = "_system/inbox/"


@router.get("/inbox", response_class=HTMLResponse)
def inbox_list(request: Request, container: ContainerDep) -> HTMLResponse:
    pending = container.inbox_reader.list_pending()
    # Provide a normalised "slot_basename" for URL building (the part after _system/inbox/).
    items = [
        {
            "slot_basename": p.slot_id.removeprefix(_INBOX_PREFIX),
            "subject": p.subject,
            "from_address": p.from_address,
            "received_at": p.received_at,
            "attachment_count": len(p.attachment_keys),
        }
        for p in pending
    ]
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "inbox.html", {"items": items})


@router.get("/inbox/{slot}", response_class=HTMLResponse)
def inbox_detail(
    request: Request,
    container: ContainerDep,
    slot: str,
) -> HTMLResponse:
    full_slot = f"{_INBOX_PREFIX}{slot}"
    try:
        parked = container.inbox_reader.get(full_slot)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    attachments = [
        {
            "filename": k.rsplit("/", 1)[1],
            "key": k,
        }
        for k in parked.attachment_keys
    ]
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "inbox_detail.html",
        {"parked": parked, "slot_basename": slot, "attachments": attachments},
    )


@router.get("/inbox/{slot}/attachments/{filename}")
def inbox_attachment(
    container: ContainerDep,
    slot: str,
    filename: str,
) -> Response:
    key = f"{_INBOX_PREFIX}{slot}/{filename}"
    if not container.backend.exists(key):
        raise HTTPException(status_code=404, detail="attachment not found")
    raw = container.backend.read_bytes(key)
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return Response(content=raw, media_type=mime)
