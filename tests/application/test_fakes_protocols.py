from edelrep.domain.ports import (
    ImageRepository,
    RepairRepository,
    VehicleRepository,
)

from .fakes import InMemoryImageRepo, InMemoryRepairRepo, InMemoryVehicleRepo


def test_vehicle_repo_satisfies_protocol() -> None:
    repo: VehicleRepository = InMemoryVehicleRepo()
    assert isinstance(repo, VehicleRepository)


def test_repair_repo_satisfies_protocol() -> None:
    repo: RepairRepository = InMemoryRepairRepo()
    assert isinstance(repo, RepairRepository)


def test_image_repo_satisfies_protocol() -> None:
    repo: ImageRepository = InMemoryImageRepo()
    assert isinstance(repo, ImageRepository)
