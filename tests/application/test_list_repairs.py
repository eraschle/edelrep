from datetime import UTC, date, datetime

import pytest
from ulid import ULID

from edelrep.application.list_repairs import ListRepairsUseCase
from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.exceptions import VehicleNotFound
from edelrep.domain.value_objects import VehicleId

from .fakes import InMemoryRepairRepo, InMemoryVehicleRepo


def test_returns_empty_for_vehicle_with_no_repairs(
    vehicle_repo: InMemoryVehicleRepo,
    repair_repo: InMemoryRepairRepo,
    sample_vehicle: Vehicle,
) -> None:
    vehicle_repo.save(sample_vehicle)
    use_case = ListRepairsUseCase(vehicle_repo, repair_repo)
    assert use_case.execute(sample_vehicle.id) == []


def test_returns_repairs_newest_first(
    vehicle_repo: InMemoryVehicleRepo,
    repair_repo: InMemoryRepairRepo,
    sample_vehicle: Vehicle,
) -> None:
    vehicle_repo.save(sample_vehicle)
    older = Repair(
        id=ULID(),
        vehicle_id=sample_vehicle.id,
        date=date(2026, 1, 1),
        description="old",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = Repair(
        id=ULID(),
        vehicle_id=sample_vehicle.id,
        date=date(2026, 5, 1),
        description="new",
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    repair_repo.save(older)
    repair_repo.save(newer)

    use_case = ListRepairsUseCase(vehicle_repo, repair_repo)
    results = use_case.execute(sample_vehicle.id)
    assert [r.description for r in results] == ["new", "old"]


def test_raises_when_vehicle_missing(
    vehicle_repo: InMemoryVehicleRepo,
    repair_repo: InMemoryRepairRepo,
) -> None:
    use_case = ListRepairsUseCase(vehicle_repo, repair_repo)
    with pytest.raises(VehicleNotFound):
        use_case.execute(VehicleId("99999"))
