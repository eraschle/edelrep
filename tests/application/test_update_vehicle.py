from datetime import UTC, datetime

import pytest
from ulid import ULID

from edelrep.application.create_vehicle import CreateVehicleUseCase
from edelrep.application.update_vehicle import UpdateVehicleUseCase
from edelrep.domain.entities import Vehicle
from edelrep.domain.exceptions import (
    DuplicateRegistrationNumber,
    DuplicateVin,
    InvalidRegistrationNumber,
    InvalidVin,
    VehicleIdentifierRequired,
    VehicleNotFound,
)
from edelrep.infrastructure.search.in_memory import InMemorySearchIndex

from .fakes import InMemoryVehicleRepo


def _now() -> datetime:
    return datetime(2026, 5, 1, tzinfo=UTC)


def _seed(vehicle_repo: InMemoryVehicleRepo, **overrides) -> Vehicle:
    defaults: dict[str, object] = {
        "id": ULID(),
        "registration_number": "12345",
        "vin": None,
        "description": None,
        "created_at": _now(),
    }
    defaults.update(overrides)
    vehicle = Vehicle(**defaults)  # type: ignore[arg-type]
    vehicle_repo.save(vehicle)
    return vehicle


def test_update_changes_all_editable_fields(vehicle_repo: InMemoryVehicleRepo) -> None:
    seeded = _seed(vehicle_repo, vin="OLDVIN", description="alt")
    search_index = InMemorySearchIndex()
    search_index.upsert_vehicle(seeded)

    uc = UpdateVehicleUseCase(vehicle_repo, search_index)
    updated = uc.execute(
        vehicle_id=seeded.id,
        registration_number="67890",
        vin="NEWVIN",
        description="neu",
    )

    assert updated.id == seeded.id
    assert updated.registration_number == "67890"
    assert updated.vin == "NEWVIN"
    assert updated.description == "neu"
    assert vehicle_repo.get(seeded.id).registration_number == "67890"


def test_update_preserves_created_at(vehicle_repo: InMemoryVehicleRepo) -> None:
    seeded = _seed(vehicle_repo)
    search_index = InMemorySearchIndex()
    uc = UpdateVehicleUseCase(vehicle_repo, search_index)
    updated = uc.execute(
        vehicle_id=seeded.id,
        registration_number="99999",
        vin=None,
        description=None,
    )
    assert updated.created_at == seeded.created_at


def test_update_keeping_same_values_is_allowed(vehicle_repo: InMemoryVehicleRepo) -> None:
    seeded = _seed(vehicle_repo, vin="WDB123")
    search_index = InMemorySearchIndex()
    uc = UpdateVehicleUseCase(vehicle_repo, search_index)
    # Same values must not trigger the unique guard against itself.
    updated = uc.execute(
        vehicle_id=seeded.id,
        registration_number="12345",
        vin="WDB123",
        description=None,
    )
    assert updated.registration_number == "12345"
    assert updated.vin == "WDB123"


def test_update_rejects_when_both_identifiers_cleared(
    vehicle_repo: InMemoryVehicleRepo,
) -> None:
    seeded = _seed(vehicle_repo, vin="WDB123")
    uc = UpdateVehicleUseCase(vehicle_repo, InMemorySearchIndex())
    with pytest.raises(VehicleIdentifierRequired):
        uc.execute(
            vehicle_id=seeded.id,
            registration_number=None,
            vin=None,
            description="trotzdem da",
        )


def test_update_rejects_invalid_registration(vehicle_repo: InMemoryVehicleRepo) -> None:
    seeded = _seed(vehicle_repo)
    uc = UpdateVehicleUseCase(vehicle_repo, InMemorySearchIndex())
    with pytest.raises(InvalidRegistrationNumber):
        uc.execute(
            vehicle_id=seeded.id,
            registration_number="with space",
            vin=None,
            description=None,
        )


def test_update_rejects_invalid_vin(vehicle_repo: InMemoryVehicleRepo) -> None:
    seeded = _seed(vehicle_repo)
    uc = UpdateVehicleUseCase(vehicle_repo, InMemorySearchIndex())
    with pytest.raises(InvalidVin):
        uc.execute(
            vehicle_id=seeded.id,
            registration_number="12345",
            vin="with space",
            description=None,
        )


def test_update_rejects_duplicate_registration(vehicle_repo: InMemoryVehicleRepo) -> None:
    _seed(vehicle_repo, registration_number="11111")
    target = _seed(vehicle_repo, registration_number="22222")
    uc = UpdateVehicleUseCase(vehicle_repo, InMemorySearchIndex())
    with pytest.raises(DuplicateRegistrationNumber):
        uc.execute(
            vehicle_id=target.id,
            registration_number="11111",
            vin=None,
            description=None,
        )


def test_update_rejects_duplicate_vin(vehicle_repo: InMemoryVehicleRepo) -> None:
    _seed(vehicle_repo, registration_number="11111", vin="VIN1")
    target = _seed(vehicle_repo, registration_number="22222", vin="VIN2")
    uc = UpdateVehicleUseCase(vehicle_repo, InMemorySearchIndex())
    with pytest.raises(DuplicateVin):
        uc.execute(
            vehicle_id=target.id,
            registration_number="22222",
            vin="VIN1",
            description=None,
        )


def test_update_unknown_vehicle_raises(vehicle_repo: InMemoryVehicleRepo) -> None:
    uc = UpdateVehicleUseCase(vehicle_repo, InMemorySearchIndex())
    with pytest.raises(VehicleNotFound):
        uc.execute(
            vehicle_id=ULID(),
            registration_number="12345",
            vin=None,
            description=None,
        )


def test_update_reprojects_into_search_index(vehicle_repo: InMemoryVehicleRepo) -> None:
    seeded = _seed(vehicle_repo, description="alt")
    search_index = InMemorySearchIndex()
    search_index.upsert_vehicle(seeded)
    uc = UpdateVehicleUseCase(vehicle_repo, search_index)
    uc.execute(
        vehicle_id=seeded.id,
        registration_number="12345",
        vin=None,
        description="neue Bezeichnung mit Kran",
    )
    hits = list(search_index.search_vehicles("Kran"))
    assert [v.id for v in hits] == [seeded.id]


def test_create_then_update_via_use_cases(vehicle_repo: InMemoryVehicleRepo) -> None:
    search_index = InMemorySearchIndex()
    creator = CreateVehicleUseCase(vehicle_repo, search_index)
    updater = UpdateVehicleUseCase(vehicle_repo, search_index)
    created = creator.execute(registration_number="12345", vin=None, description=None)
    updated = updater.execute(
        vehicle_id=created.id,
        registration_number="12345",
        vin="WDB99999",
        description="Kran",
    )
    assert updated.vin == "WDB99999"
    assert updated.description == "Kran"
