from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from edelrep.presentation.app_factory import create_app
from edelrep.presentation.container import Container, build_container


@pytest.fixture
def container(tmp_path: Path) -> Iterator[Container]:
    storage = tmp_path / "store"
    index = tmp_path / "index.db"
    c = build_container(storage, index, with_live_index=False)
    yield c
    c.projector.connection.close()


@pytest.fixture
def client(container: Container) -> Iterator[TestClient]:
    app = create_app(container)
    with TestClient(app) as test_client:
        yield test_client
