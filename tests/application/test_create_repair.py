from datetime import UTC, date, datetime

import pytest

from edelrep.application.create_repair import CreateRepairUseCase
from edelrep.domain.entities import Vehicle
from edelrep.domain.exceptions import VehicleNotFound
from edelrep.domain.value_objects import VehicleId

from .fakes import InMemoryRepairRepo, InMemoryVehicleRepo


def test_creates_repair_for_existing_vehicle() -> None:
    vrepo = InMemoryVehicleRepo()
    rrepo = InMemoryRepairRepo()
    vrepo.save(
        Vehicle(
            id=VehicleId("12345"),
            vin=None,
            description=None,
            created_at=datetime(2026, 5, 3, tzinfo=UTC),
        )
    )
    use_case = CreateRepairUseCase(vrepo, rrepo)
    repair = use_case.execute(
        vehicle_id=VehicleId("12345"),
        repair_date=date(2026, 5, 3),
        description="brakes",
    )
    assert repair.vehicle_id == VehicleId("12345")
    assert repair.description == "brakes"
    assert repair.date == date(2026, 5, 3)


def test_raises_when_vehicle_missing() -> None:
    vrepo = InMemoryVehicleRepo()
    rrepo = InMemoryRepairRepo()
    use_case = CreateRepairUseCase(vrepo, rrepo)
    with pytest.raises(VehicleNotFound):
        use_case.execute(
            vehicle_id=VehicleId("99999"),
            repair_date=date(2026, 5, 3),
            description="brakes",
        )


def test_repair_id_is_unique_per_call() -> None:
    vrepo = InMemoryVehicleRepo()
    rrepo = InMemoryRepairRepo()
    vrepo.save(
        Vehicle(
            id=VehicleId("12345"),
            vin=None,
            description=None,
            created_at=datetime(2026, 5, 3, tzinfo=UTC),
        )
    )
    use_case = CreateRepairUseCase(vrepo, rrepo)
    r1 = use_case.execute(
        vehicle_id=VehicleId("12345"),
        repair_date=date(2026, 5, 1),
        description="first",
    )
    r2 = use_case.execute(
        vehicle_id=VehicleId("12345"),
        repair_date=date(2026, 5, 2),
        description="second",
    )
    assert r1.id != r2.id
