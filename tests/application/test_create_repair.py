from datetime import UTC, date, datetime

import pytest
from ulid import ULID

from edelrep.application.create_repair import CreateRepairUseCase
from edelrep.domain.entities import Vehicle
from edelrep.domain.exceptions import VehicleNotFound

from .fakes import InMemoryRepairRepo, InMemoryVehicleRepo


def test_creates_repair_for_existing_vehicle() -> None:
    vrepo = InMemoryVehicleRepo()
    rrepo = InMemoryRepairRepo()
    vehicle = Vehicle(
        id=ULID(),
        registration_number="12345",
        vin=None,
        description=None,
        created_at=datetime(2026, 5, 3, tzinfo=UTC),
    )
    vrepo.save(vehicle)
    use_case = CreateRepairUseCase(vrepo, rrepo)
    repair = use_case.execute(
        vehicle_id=vehicle.id,
        repair_date=date(2026, 5, 3),
        description="brakes",
    )
    assert repair.vehicle_id == vehicle.id
    assert repair.description == "brakes"
    assert repair.date == date(2026, 5, 3)


def test_raises_when_vehicle_missing() -> None:
    vrepo = InMemoryVehicleRepo()
    rrepo = InMemoryRepairRepo()
    use_case = CreateRepairUseCase(vrepo, rrepo)
    with pytest.raises(VehicleNotFound):
        use_case.execute(
            vehicle_id=ULID(),
            repair_date=date(2026, 5, 3),
            description="brakes",
        )


def test_repair_id_is_unique_per_call() -> None:
    vrepo = InMemoryVehicleRepo()
    rrepo = InMemoryRepairRepo()
    vehicle = Vehicle(
        id=ULID(),
        registration_number="12345",
        vin=None,
        description=None,
        created_at=datetime(2026, 5, 3, tzinfo=UTC),
    )
    vrepo.save(vehicle)
    use_case = CreateRepairUseCase(vrepo, rrepo)
    r1 = use_case.execute(
        vehicle_id=vehicle.id,
        repair_date=date(2026, 5, 1),
        description="first",
    )
    r2 = use_case.execute(
        vehicle_id=vehicle.id,
        repair_date=date(2026, 5, 2),
        description="second",
    )
    assert r1.id != r2.id
