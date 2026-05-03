from typing import Annotated

from fastapi import Depends, Request

from edelrep.application import (
    GetImageUseCase,
    ListRepairsUseCase,
    SearchVehicleUseCase,
    UploadImageUseCase,
)
from edelrep.application.create_repair import CreateRepairUseCase
from edelrep.application.create_vehicle import CreateVehicleUseCase
from edelrep.presentation.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container  # type: ignore[no-any-return]


ContainerDep = Annotated[Container, Depends(get_container)]


def get_create_vehicle(c: ContainerDep) -> CreateVehicleUseCase:
    return c.create_vehicle


def get_create_repair(c: ContainerDep) -> CreateRepairUseCase:
    return c.create_repair


def get_upload_image(c: ContainerDep) -> UploadImageUseCase:
    return c.upload_image


def get_list_repairs(c: ContainerDep) -> ListRepairsUseCase:
    return c.list_repairs


def get_get_image(c: ContainerDep) -> GetImageUseCase:
    return c.get_image


def get_search_vehicle(c: ContainerDep) -> SearchVehicleUseCase:
    return c.search_vehicle
