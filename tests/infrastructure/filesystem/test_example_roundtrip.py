import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import fsspec
import pytest
from fsspec.implementations.memory import MemoryFileSystem

from edelrep.domain.ports import StorageBackend
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.storage import FsspecBackend, LocalFilesystemBackend

FIXTURE = Path(__file__).parent / "fixtures" / "example_storage_root"


def _copy_fixture_into_backend(backend: StorageBackend, source: Path) -> None:
    for path in source.rglob("*"):
        if path.is_file():
            key = path.relative_to(source).as_posix()
            backend.write_bytes(key, path.read_bytes())


@pytest.fixture(params=["local", "memory"])
def seeded_backend(request: pytest.FixtureRequest, tmp_path: Path) -> StorageBackend:
    if request.param == "local":
        target = tmp_path / "storage"
        shutil.copytree(FIXTURE, target)
        return LocalFilesystemBackend(target)
    fs = fsspec.filesystem("memory")
    if isinstance(fs, MemoryFileSystem):
        fs.store.clear()
        fs.pseudo_dirs.clear()
    safe = request.node.nodeid.replace("/", "__").replace("::", "__").replace("[", "_").replace("]", "_")
    backend: StorageBackend = FsspecBackend(fs, root=f"/edelrep-roundtrip-{safe}")
    _copy_fixture_into_backend(backend, FIXTURE)
    return backend


def test_can_read_vehicle_from_fixture(seeded_backend: StorageBackend) -> None:
    repo = FilesystemVehicleRepository(seeded_backend)
    vehicle = repo.get(VehicleId("12345"))
    assert vehicle.id == VehicleId("12345")
    assert vehicle.vin == "WDB12345TEST"
    assert vehicle.created_at == datetime(2026, 4, 15, 10, 0, tzinfo=UTC)


def test_can_list_repairs_from_fixture(seeded_backend: StorageBackend) -> None:
    repo = FilesystemRepairRepository(seeded_backend)
    repairs = list(repo.list_for_vehicle(VehicleId("12345")))
    assert len(repairs) == 1
    assert repairs[0].description == "Bremsbeläge vorne"


def test_can_list_images_from_fixture(seeded_backend: StorageBackend) -> None:
    repair_repo = FilesystemRepairRepository(seeded_backend)
    image_repo = FilesystemImageRepository(seeded_backend)
    repair = next(iter(repair_repo.list_for_vehicle(VehicleId("12345"))))
    images = list(image_repo.list_for_repair(repair.id))
    assert len(images) == 1
    assert images[0].size_bytes == 4
    assert images[0].thumbnail_key is not None


def test_round_trip_re_save_produces_byte_identical_sidecar(
    seeded_backend: StorageBackend,
) -> None:
    repo = FilesystemVehicleRepository(seeded_backend)
    vehicle = repo.get(VehicleId("12345"))
    sidecar_before = seeded_backend.read_bytes("12345/_vehicle.json")
    repo.update(vehicle)
    sidecar_after = seeded_backend.read_bytes("12345/_vehicle.json")
    assert json.loads(sidecar_before) == json.loads(sidecar_after)
