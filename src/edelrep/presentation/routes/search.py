from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from edelrep.presentation.dependencies import ContainerDep

router = APIRouter()


@router.get("/search", response_class=HTMLResponse)
def search_page(request: Request, container: ContainerDep) -> HTMLResponse:
    templates = request.app.state.templates
    results = container.search_vehicle.execute("", limit=200)
    return templates.TemplateResponse(
        request,
        "search.html",
        {"results": results, "is_empty_filter": False},
    )


@router.get("/search/suggestions", response_class=HTMLResponse)
def suggestions(
    request: Request,
    container: ContainerDep,
    q: str = "",
) -> HTMLResponse:
    templates = request.app.state.templates
    results = container.search_vehicle.execute(q)
    return templates.TemplateResponse(
        request,
        "_vehicle_search_results.html",
        {"results": results, "is_empty_filter": bool(q.strip())},
    )
