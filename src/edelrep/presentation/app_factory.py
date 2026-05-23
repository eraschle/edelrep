from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from edelrep.presentation.container import Container
from edelrep.presentation.routes import home, images, inbox, repairs, search, vehicles

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    container: Container = app.state.container
    if container.live_index is not None:
        container.live_index.start()
    if container.email_poller is not None:
        container.email_poller.start()
    if container.cleanup_scheduler is not None:
        container.cleanup_scheduler.start()
    try:
        yield
    finally:
        if container.cleanup_scheduler is not None:
            container.cleanup_scheduler.stop()
        if container.email_poller is not None:
            container.email_poller.stop()
        if container.live_index is not None:
            container.live_index.stop()


def create_app(container: Container) -> FastAPI:
    """Build the edelrep FastAPI app wired to the given container."""
    app = FastAPI(title="edelrep", lifespan=_lifespan)
    app.state.container = container
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    app.include_router(home.router)
    app.include_router(search.router)
    app.include_router(vehicles.router)
    app.include_router(repairs.router)
    app.include_router(images.router)
    app.include_router(inbox.router)

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    return app
