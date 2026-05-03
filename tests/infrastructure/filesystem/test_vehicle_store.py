import pytest

from edelrep.domain.entities import Vehicle
from edelrep.domain.exceptions import (
    DuplicateVehicle,
    SidecarSchemaError,
    VehicleNotFound,
)
from edelrep.domain.ports import StorageBackend, VehicleRepository
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.vehicle_store import FilesystemVehicleRepository


def test_save_and_get_round_trips(backend: StorageBackend, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(backend)
    repo.save(sample_vehicle)
    assert repo.get(sample_vehicle.id) == sample_vehicle


def test_save_creates_sidecar_with_expected_layout(backend: StorageBackend, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(backend)
    repo.save(sample_vehicle)
    assert backend.exists("12345/_vehicle.json")


def test_save_raises_duplicate_when_sidecar_exists(backend: StorageBackend, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(backend)
    repo.save(sample_vehicle)
    with pytest.raises(DuplicateVehicle):
        repo.save(sample_vehicle)


def test_get_raises_when_missing(backend: StorageBackend) -> None:
    repo = FilesystemVehicleRepository(backend)
    with pytest.raises(VehicleNotFound):
        repo.get(VehicleId("99999"))


def test_get_raises_schema_error_on_bad_sidecar(backend: StorageBackend, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(backend)
    repo.save(sample_vehicle)
    backend.write_bytes("12345/_vehicle.json", b'{"schema_version": 99, "vin": "x"}')
    with pytest.raises(SidecarSchemaError):
        repo.get(sample_vehicle.id)


def test_update_existing_vehicle(backend: StorageBackend, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(backend)
    repo.save(sample_vehicle)
    updated = Vehicle(
        id=sample_vehicle.id,
        vin="NEWVIN",
        description="Updated",
        created_at=sample_vehicle.created_at,
    )
    repo.update(updated)
    assert repo.get(sample_vehicle.id) == updated


def test_update_raises_when_missing(backend: StorageBackend, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(backend)
    with pytest.raises(VehicleNotFound):
        repo.update(sample_vehicle)


def test_exists(backend: StorageBackend, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(backend)
    assert not repo.exists(sample_vehicle.id)
    repo.save(sample_vehicle)
    assert repo.exists(sample_vehicle.id)


def test_list_all_skips_underscore_prefixed_keys(backend: StorageBackend, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(backend)
    repo.save(sample_vehicle)
    backend.write_bytes("_system/inbox/foo.eml", b"")
    listed = list(repo.list_all())
    assert listed == [sample_vehicle]


def test_list_all_skips_keys_without_vehicle_sidecar(
    backend: StorageBackend, sample_vehicle: Vehicle
) -> None:
    repo = FilesystemVehicleRepository(backend)
    repo.save(sample_vehicle)
    # Vehicle directory shape but no sidecar.
    backend.write_bytes("67890/random.txt", b"")
    listed = list(repo.list_all())
    assert listed == [sample_vehicle]


def test_list_all_returns_empty_when_root_empty(backend: StorageBackend) -> None:
    repo = FilesystemVehicleRepository(backend)
    assert list(repo.list_all()) == []


def test_list_all_skips_invalid_vehicle_id_prefix(backend: StorageBackend, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(backend)
    repo.save(sample_vehicle)
    # The "with space" prefix would fail VehicleId validation if the regex were lax,
    # but is_vehicle_sidecar_key already rejects it via the character class.
    # Seed a key with leading-dot prefix instead, which is rejected by the predicate.
    backend.write_bytes(".bad/_vehicle.json", b'{"schema_version": 1}')
    listed = list(repo.list_all())
    assert listed == [sample_vehicle]


def test_satisfies_protocol(backend: StorageBackend) -> None:
    repo: VehicleRepository = FilesystemVehicleRepository(backend)
    assert isinstance(repo, VehicleRepository)
