from typing import Annotated

from fastapi import Depends, Request

from edelrep.presentation.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container  # type: ignore[no-any-return]


ContainerDep = Annotated[Container, Depends(get_container)]
