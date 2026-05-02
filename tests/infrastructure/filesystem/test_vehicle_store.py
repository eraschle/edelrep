from pathlib import Path

import pytest

from edelrep.domain.entities import Vehicle
from edelrep.domain.exceptions import (
    DuplicateVehicle,
    SidecarSchemaError,
    VehicleNotFound,
)
from edelrep.domain.ports import VehicleRepository
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.vehicle_store import FilesystemVehicleRepository


def test_save_and_get_round_trips(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    repo.save(sample_vehicle)
    assert repo.get(sample_vehicle.id) == sample_vehicle


def test_save_creates_sidecar_with_expected_layout(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    repo.save(sample_vehicle)
    sidecar = storage_root / "12345" / "_vehicle.json"
    assert sidecar.is_file()


def test_save_raises_duplicate_when_folder_exists(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    repo.save(sample_vehicle)
    with pytest.raises(DuplicateVehicle):
        repo.save(sample_vehicle)


def test_get_raises_when_missing(storage_root: Path) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    with pytest.raises(VehicleNotFound):
        repo.get(VehicleId("99999"))


def test_get_raises_schema_error_on_bad_sidecar(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    repo.save(sample_vehicle)
    sidecar = storage_root / "12345" / "_vehicle.json"
    sidecar.write_text('{"schema_version": 99, "vin": "x"}', encoding="utf-8")
    with pytest.raises(SidecarSchemaError):
        repo.get(sample_vehicle.id)


def test_update_existing_vehicle(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    repo.save(sample_vehicle)
    updated = Vehicle(
        id=sample_vehicle.id,
        vin="NEWVIN",
        description="Updated",
        created_at=sample_vehicle.created_at,
    )
    repo.update(updated)
    assert repo.get(sample_vehicle.id) == updated


def test_update_raises_when_missing(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    with pytest.raises(VehicleNotFound):
        repo.update(sample_vehicle)


def test_exists(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    assert not repo.exists(sample_vehicle.id)
    repo.save(sample_vehicle)
    assert repo.exists(sample_vehicle.id)


def test_list_all_skips_underscore_prefixed_dirs(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    repo.save(sample_vehicle)
    (storage_root / "_system").mkdir()
    (storage_root / "_system" / "inbox").mkdir()
    listed = list(repo.list_all())
    assert listed == [sample_vehicle]


def test_list_all_skips_directory_without_sidecar(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    repo.save(sample_vehicle)
    (storage_root / "67890").mkdir()  # malformed: no _vehicle.json
    listed = list(repo.list_all())
    assert listed == [sample_vehicle]


def test_list_all_returns_empty_when_root_missing(tmp_path: Path) -> None:
    repo = FilesystemVehicleRepository(tmp_path / "nonexistent")
    assert list(repo.list_all()) == []


def test_list_all_skips_dir_with_invalid_vehicle_id_name(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    repo.save(sample_vehicle)
    bad = storage_root / "with space"
    bad.mkdir()
    (bad / "_vehicle.json").write_text(
        '{"schema_version": 1, "registration_number": "with space", "vin": null, "description": null, "created_at": "2026-04-15T10:00:00+00:00"}',
        encoding="utf-8",
    )
    listed = list(repo.list_all())
    assert listed == [sample_vehicle]


def test_satisfies_protocol(storage_root: Path) -> None:
    repo: VehicleRepository = FilesystemVehicleRepository(storage_root)
    assert isinstance(repo, VehicleRepository)
