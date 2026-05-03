from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/")
def index() -> RedirectResponse:
    return RedirectResponse(url="/search", status_code=302)
