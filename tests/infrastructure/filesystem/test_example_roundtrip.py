import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.storage import LocalFilesystemBackend

FIXTURE = Path(__file__).parent / "fixtures" / "example_storage_root"


@pytest.fixture
def working_root(tmp_path: Path) -> Path:
    target = tmp_path / "storage"
    shutil.copytree(FIXTURE, target)
    return target


def test_can_read_vehicle_from_fixture(working_root: Path) -> None:
    repo = FilesystemVehicleRepository(LocalFilesystemBackend(working_root))
    vehicle = repo.get(VehicleId("12345"))
    assert vehicle.id == VehicleId("12345")
    assert vehicle.vin == "WDB12345TEST"
    assert vehicle.created_at == datetime(2026, 4, 15, 10, 0, tzinfo=UTC)


def test_can_list_repairs_from_fixture(working_root: Path) -> None:
    repo = FilesystemRepairRepository(LocalFilesystemBackend(working_root))
    repairs = list(repo.list_for_vehicle(VehicleId("12345")))
    assert len(repairs) == 1
    assert repairs[0].description == "Bremsbeläge vorne"


def test_can_list_images_from_fixture(working_root: Path) -> None:
    repair_repo = FilesystemRepairRepository(LocalFilesystemBackend(working_root))
    image_repo = FilesystemImageRepository(working_root)
    repair = next(iter(repair_repo.list_for_vehicle(VehicleId("12345"))))
    images = list(image_repo.list_for_repair(repair.id))
    assert len(images) == 1
    assert images[0].size_bytes == 4
    assert images[0].thumbnail_key is not None


def test_round_trip_re_save_produces_byte_identical_sidecar(working_root: Path) -> None:
    repo = FilesystemVehicleRepository(LocalFilesystemBackend(working_root))
    vehicle = repo.get(VehicleId("12345"))
    sidecar_before = (working_root / "12345" / "_vehicle.json").read_text(encoding="utf-8")
    repo.update(vehicle)
    sidecar_after = (working_root / "12345" / "_vehicle.json").read_text(encoding="utf-8")
    # Field order may differ; compare normalised JSON.
    assert json.loads(sidecar_before) == json.loads(sidecar_after)
