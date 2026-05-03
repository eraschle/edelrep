from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from edelrep.presentation.container import Container

_TEMPLATES_DIR = Path(__file__).parent / "templates"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    container: Container = app.state.container
    if container.live_index is not None:
        container.live_index.start()
    try:
        yield
    finally:
        if container.live_index is not None:
            container.live_index.stop()


def create_app(container: Container) -> FastAPI:
    """Build the edelrep FastAPI app wired to the given container."""
    app = FastAPI(title="edelrep", lifespan=_lifespan)
    app.state.container = container
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    # Routes are registered as they're added in P7.6-P7.9.
    return app
