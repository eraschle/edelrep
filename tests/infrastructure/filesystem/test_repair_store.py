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
from edelrep.domain.ports import RepairRepository
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.repair_store import FilesystemRepairRepository
from edelrep.infrastructure.filesystem.vehicle_store import FilesystemVehicleRepository


def _seed_vehicle(root: Path, sample_vehicle: Vehicle) -> None:
    FilesystemVehicleRepository(root).save(sample_vehicle)


def test_save_and_get(storage_root: Path, sample_vehicle: Vehicle, sample_repair: Repair) -> None:
    _seed_vehicle(storage_root, sample_vehicle)
    repo = FilesystemRepairRepository(storage_root)
    repo.save(sample_repair)
    fetched = repo.get(sample_repair.id)
    assert fetched == sample_repair


def test_save_raises_when_vehicle_missing(storage_root: Path, sample_repair: Repair) -> None:
    repo = FilesystemRepairRepository(storage_root)
    with pytest.raises(VehicleNotFound):
        repo.save(sample_repair)


def test_save_raises_duplicate_on_collision(
    storage_root: Path, sample_vehicle: Vehicle, sample_repair: Repair
) -> None:
    _seed_vehicle(storage_root, sample_vehicle)
    repo = FilesystemRepairRepository(storage_root)
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


def test_get_raises_when_missing(storage_root: Path) -> None:
    repo = FilesystemRepairRepository(storage_root)
    with pytest.raises(RepairNotFound):
        repo.get(ULID())


def test_update_existing(storage_root: Path, sample_vehicle: Vehicle, sample_repair: Repair) -> None:
    _seed_vehicle(storage_root, sample_vehicle)
    repo = FilesystemRepairRepository(storage_root)
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


def test_update_raises_when_missing(storage_root: Path, sample_repair: Repair) -> None:
    repo = FilesystemRepairRepository(storage_root)
    with pytest.raises(RepairNotFound):
        repo.update(sample_repair)


def test_list_for_vehicle_orders_newest_first(
    storage_root: Path,
    sample_vehicle: Vehicle,
) -> None:
    _seed_vehicle(storage_root, sample_vehicle)
    repo = FilesystemRepairRepository(storage_root)
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


def test_list_for_vehicle_returns_empty_for_unknown(storage_root: Path) -> None:
    repo = FilesystemRepairRepository(storage_root)
    assert list(repo.list_for_vehicle(VehicleId("99999"))) == []


def test_satisfies_protocol(storage_root: Path) -> None:
    repo: RepairRepository = FilesystemRepairRepository(storage_root)
    assert isinstance(repo, RepairRepository)
