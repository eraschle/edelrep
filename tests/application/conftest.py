from datetime import UTC, date, datetime

import pytest
from ulid import ULID

from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.value_objects import VehicleId

from .fakes import InMemoryImageRepo, InMemoryRepairRepo, InMemoryVehicleRepo


@pytest.fixture
def vehicle_repo() -> InMemoryVehicleRepo:
    return InMemoryVehicleRepo()


@pytest.fixture
def repair_repo() -> InMemoryRepairRepo:
    return InMemoryRepairRepo()


@pytest.fixture
def image_repo() -> InMemoryImageRepo:
    return InMemoryImageRepo()


@pytest.fixture
def sample_vehicle() -> Vehicle:
    return Vehicle(
        id=VehicleId("12345"),
        vin="WDB12345TEST",
        description="Kran 4-achsig",
        created_at=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_repair() -> Repair:
    return Repair(
        id=ULID.from_str("01J9TGZP6X2K0V3W7Y8Z4QABCD"),
        vehicle_id=VehicleId("12345"),
        date=date(2026, 4, 15),
        description="Bremsbeläge vorne",
        created_at=datetime(2026, 4, 15, 16, 30, tzinfo=UTC),
    )
