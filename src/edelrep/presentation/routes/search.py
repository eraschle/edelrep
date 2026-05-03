from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from edelrep.presentation.dependencies import ContainerDep

router = APIRouter()


@router.get("/search", response_class=HTMLResponse)
def search_page(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "search.html", {"results": []})


@router.get("/search/suggestions", response_class=HTMLResponse)
def suggestions(
    request: Request,
    container: ContainerDep,
    q: str = "",
) -> HTMLResponse:
    templates = request.app.state.templates
    results = list(container.search_vehicle.execute(q)) if q else []
    return templates.TemplateResponse(
        request,
        "_vehicle_search_results.html",
        {"results": results},
    )
