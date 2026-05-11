from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ulid import ULID

from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.exceptions import (
    DuplicateRepair,
    RepairNotFound,
    VehicleNotFound,
)
from edelrep.domain.ports import RepairRepository, StorageBackend
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import FilesystemRepairRepository, FilesystemVehicleRepository
from edelrep.infrastructure.storage import LocalFilesystemBackend


def _seed_vehicle(backend: StorageBackend, sample_vehicle: Vehicle) -> None:
    FilesystemVehicleRepository(backend).save(sample_vehicle)


def test_save_and_get(backend: StorageBackend, sample_vehicle: Vehicle, sample_repair: Repair) -> None:
    _seed_vehicle(backend, sample_vehicle)
    repo = FilesystemRepairRepository(backend)
    repo.save(sample_repair)
    fetched = repo.get(sample_repair.id)
    assert fetched == sample_repair


def test_save_raises_when_vehicle_missing(backend: StorageBackend, sample_repair: Repair) -> None:
    repo = FilesystemRepairRepository(backend)
    with pytest.raises(VehicleNotFound):
        repo.save(sample_repair)


def test_save_raises_duplicate_on_collision(
    backend: StorageBackend, sample_vehicle: Vehicle, sample_repair: Repair
) -> None:
    _seed_vehicle(backend, sample_vehicle)
    repo = FilesystemRepairRepository(backend)
    repo.save(sample_repair)
    clash = Repair(
        id=ULID(),
        vehicle_id=sample_repair.vehicle_id,
        date=sample_repair.date,
        description=sample_repair.description,
        created_at=sample_repair.created_at,
    )
    with pytest.raises(DuplicateRepair):
        repo.save(clash)


def test_get_raises_when_missing(backend: StorageBackend) -> None:
    repo = FilesystemRepairRepository(backend)
    with pytest.raises(RepairNotFound):
        repo.get(ULID())


def test_update_existing(backend: StorageBackend, sample_vehicle: Vehicle, sample_repair: Repair) -> None:
    _seed_vehicle(backend, sample_vehicle)
    repo = FilesystemRepairRepository(backend)
    repo.save(sample_repair)
    updated = Repair(
        id=sample_repair.id,
        vehicle_id=sample_repair.vehicle_id,
        date=sample_repair.date,
        description=sample_repair.description,
        created_at=datetime(2026, 4, 16, 9, 0, tzinfo=UTC),
    )
    repo.update(updated)
    assert repo.get(sample_repair.id) == updated


def test_update_raises_when_missing(backend: StorageBackend, sample_repair: Repair) -> None:
    repo = FilesystemRepairRepository(backend)
    with pytest.raises(RepairNotFound):
        repo.update(sample_repair)


def test_list_for_vehicle_orders_newest_first(
    backend: StorageBackend,
    sample_vehicle: Vehicle,
) -> None:
    _seed_vehicle(backend, sample_vehicle)
    repo = FilesystemRepairRepository(backend)
    older = Repair(
        id=ULID(),
        vehicle_id=sample_vehicle.id,
        date=date(2026, 1, 1),
        description="old",
        created_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    newer = Repair(
        id=ULID(),
        vehicle_id=sample_vehicle.id,
        date=date(2026, 5, 1),
        description="new",
        created_at=datetime(2026, 5, 1, 0, 0, tzinfo=UTC),
    )
    repo.save(older)
    repo.save(newer)
    listed = list(repo.list_for_vehicle(sample_vehicle.id))
    assert [r.date for r in listed] == [date(2026, 5, 1), date(2026, 1, 1)]


def test_list_for_vehicle_returns_empty_for_unknown(backend: StorageBackend) -> None:
    repo = FilesystemRepairRepository(backend)
    assert list(repo.list_for_vehicle(VehicleId("99999"))) == []


def test_list_for_vehicle_empty_when_no_repairs(backend: StorageBackend, sample_vehicle: Vehicle) -> None:
    _seed_vehicle(backend, sample_vehicle)
    repo = FilesystemRepairRepository(backend)
    assert list(repo.list_for_vehicle(sample_vehicle.id)) == []


def test_list_for_vehicle_skips_non_repair_keys(
    backend: StorageBackend, sample_vehicle: Vehicle, sample_repair: Repair
) -> None:
    _seed_vehicle(backend, sample_vehicle)
    repo = FilesystemRepairRepository(backend)
    repo.save(sample_repair)
    backend.write_bytes("12345/stray.txt", b"noise")
    repairs = list(repo.list_for_vehicle(sample_vehicle.id))
    assert len(repairs) == 1


def test_satisfies_protocol(backend: StorageBackend) -> None:
    repo: RepairRepository = FilesystemRepairRepository(backend)
    assert isinstance(repo, RepairRepository)


def test_get_filters_non_repair_keys_during_scan(
    backend: StorageBackend, sample_vehicle: Vehicle, sample_repair: Repair
) -> None:
    # Seed both vehicle sidecar and stray keys; get() must skip them via is_repair_sidecar_key.
    _seed_vehicle(backend, sample_vehicle)
    repo = FilesystemRepairRepository(backend)
    repo.save(sample_repair)
    backend.write_bytes("12345/stray.txt", b"noise")
    backend.write_bytes("12345/2026-04-15__bremsbelage-vorne/extra.txt", b"more noise")
    # Should still find the repair, filtering out the noise.
    fetched = repo.get(sample_repair.id)
    assert fetched.id == sample_repair.id


def test_update_filters_mismatched_id_during_scan(
    backend: StorageBackend, sample_vehicle: Vehicle, sample_repair: Repair
) -> None:
    # Seed two repairs; updating the second should skip past the first (ULID mismatch branch).
    _seed_vehicle(backend, sample_vehicle)
    repo = FilesystemRepairRepository(backend)
    repo.save(sample_repair)
    other = Repair(
        id=ULID(),
        vehicle_id=sample_repair.vehicle_id,
        date=date(2026, 6, 1),
        description="other",
        created_at=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
    )
    repo.save(other)
    updated_other = Repair(
        id=other.id,
        vehicle_id=other.vehicle_id,
        date=other.date,
        description=other.description,
        created_at=datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
    )
    repo.update(updated_other)
    assert repo.get(other.id) == updated_other
    # The first repair must remain unchanged.
    assert repo.get(sample_repair.id).created_at == sample_repair.created_at


def test_list_for_vehicle_same_date_orders_by_created_at_desc(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path)
    vehicle_repo = FilesystemVehicleRepository(backend)
    repair_repo = FilesystemRepairRepository(backend)
    vehicle = Vehicle(id=VehicleId("12345"), vin=None, description=None, created_at=datetime.now(UTC))
    vehicle_repo.save(vehicle)

    earlier = Repair(
        id=ULID(),
        vehicle_id=vehicle.id,
        date=date(2026, 5, 10),
        description="brakes",
        created_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
    )
    later = Repair(
        id=ULID(),
        vehicle_id=vehicle.id,
        date=date(2026, 5, 10),
        description="oil change",
        created_at=datetime(2026, 5, 10, 15, 0, tzinfo=UTC),
    )
    repair_repo.save(earlier)
    repair_repo.save(later)

    results = list(repair_repo.list_for_vehicle(vehicle.id))
    assert results[0].description == "oil change"
    assert results[1].description == "brakes"
