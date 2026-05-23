from datetime import UTC, datetime, timedelta

import pytest
from ulid import ULID

from edelrep.application.delete_vehicle import (
    CleanupDeletedVehiclesUseCase,
    SoftDeleteVehicleUseCase,
)
from edelrep.domain.entities import Vehicle
from edelrep.domain.exceptions import (
    DeletionConfirmationMismatch,
    VehicleNotFound,
)
from edelrep.infrastructure.search.in_memory import InMemorySearchIndex

from .fakes import InMemoryVehicleRepo


def _now() -> datetime:
    return datetime(2026, 5, 1, tzinfo=UTC)


def _seed(repo: InMemoryVehicleRepo, **overrides) -> Vehicle:
    defaults: dict[str, object] = {
        "id": ULID(),
        "registration_number": "12345",
        "vin": None,
        "description": None,
        "created_at": _now(),
    }
    defaults.update(overrides)
    vehicle = Vehicle(**defaults)  # type: ignore[arg-type]
    repo.save(vehicle)
    return vehicle


# --- Soft delete -----------------------------------------------------------


def test_soft_delete_sets_deleted_at(vehicle_repo: InMemoryVehicleRepo) -> None:
    seeded = _seed(vehicle_repo)
    search_index = InMemorySearchIndex()
    search_index.upsert_vehicle(seeded)
    uc = SoftDeleteVehicleUseCase(vehicle_repo, search_index)
    deleted = uc.execute(vehicle_id=seeded.id, confirmation="12345")
    assert deleted.is_deleted is True
    assert deleted.deleted_at is not None


def test_soft_delete_accepts_vin_as_confirmation(
    vehicle_repo: InMemoryVehicleRepo,
) -> None:
    seeded = _seed(vehicle_repo, vin="WDB99999")
    uc = SoftDeleteVehicleUseCase(vehicle_repo, InMemorySearchIndex())
    uc.execute(vehicle_id=seeded.id, confirmation="WDB99999")


def test_soft_delete_accepts_ulid_as_confirmation(
    vehicle_repo: InMemoryVehicleRepo,
) -> None:
    seeded = _seed(vehicle_repo)
    uc = SoftDeleteVehicleUseCase(vehicle_repo, InMemorySearchIndex())
    uc.execute(vehicle_id=seeded.id, confirmation=str(seeded.id))


def test_soft_delete_rejects_mismatched_confirmation(
    vehicle_repo: InMemoryVehicleRepo,
) -> None:
    seeded = _seed(vehicle_repo)
    uc = SoftDeleteVehicleUseCase(vehicle_repo, InMemorySearchIndex())
    with pytest.raises(DeletionConfirmationMismatch):
        uc.execute(vehicle_id=seeded.id, confirmation="wrong")
    assert vehicle_repo.get(seeded.id).is_deleted is False


def test_soft_delete_strips_whitespace_in_confirmation(
    vehicle_repo: InMemoryVehicleRepo,
) -> None:
    seeded = _seed(vehicle_repo)
    uc = SoftDeleteVehicleUseCase(vehicle_repo, InMemorySearchIndex())
    uc.execute(vehicle_id=seeded.id, confirmation="  12345  ")


def test_soft_delete_removes_from_search_index(
    vehicle_repo: InMemoryVehicleRepo,
) -> None:
    seeded = _seed(vehicle_repo, description="Kran")
    search_index = InMemorySearchIndex()
    search_index.upsert_vehicle(seeded)
    uc = SoftDeleteVehicleUseCase(vehicle_repo, search_index)
    uc.execute(vehicle_id=seeded.id, confirmation="12345")
    assert list(search_index.search_vehicles("Kran")) == []


def test_soft_delete_unknown_vehicle_raises(
    vehicle_repo: InMemoryVehicleRepo,
) -> None:
    uc = SoftDeleteVehicleUseCase(vehicle_repo, InMemorySearchIndex())
    with pytest.raises(VehicleNotFound):
        uc.execute(vehicle_id=ULID(), confirmation="12345")


def test_soft_deleted_vehicle_is_hidden_from_default_listing(
    vehicle_repo: InMemoryVehicleRepo,
) -> None:
    seeded = _seed(vehicle_repo)
    uc = SoftDeleteVehicleUseCase(vehicle_repo, InMemorySearchIndex())
    uc.execute(vehicle_id=seeded.id, confirmation="12345")
    assert list(vehicle_repo.list_all()) == []
    assert len(list(vehicle_repo.list_all(include_deleted=True))) == 1


def test_soft_deleted_vehicle_is_invisible_to_find_by_registration(
    vehicle_repo: InMemoryVehicleRepo,
) -> None:
    seeded = _seed(vehicle_repo)
    uc = SoftDeleteVehicleUseCase(vehicle_repo, InMemorySearchIndex())
    uc.execute(vehicle_id=seeded.id, confirmation="12345")
    assert vehicle_repo.find_by_registration("12345") is None


# --- Cleanup ---------------------------------------------------------------


def test_cleanup_removes_only_old_soft_deletes(
    vehicle_repo: InMemoryVehicleRepo,
) -> None:
    old = _seed(vehicle_repo, registration_number="OLD")
    recent = _seed(vehicle_repo, registration_number="RECENT")
    not_deleted = _seed(vehicle_repo, registration_number="ACTIVE")
    # Manually flag deletions at different ages.
    now = datetime(2026, 5, 1, tzinfo=UTC)
    vehicle_repo.update(
        Vehicle(
            id=old.id,
            registration_number="OLD",
            vin=None,
            description=None,
            created_at=old.created_at,
            deleted_at=now - timedelta(days=45),
        )
    )
    vehicle_repo.update(
        Vehicle(
            id=recent.id,
            registration_number="RECENT",
            vin=None,
            description=None,
            created_at=recent.created_at,
            deleted_at=now - timedelta(days=10),
        )
    )
    uc = CleanupDeletedVehiclesUseCase(vehicle_repo, InMemorySearchIndex())
    stats = uc.execute(retention_days=30, now=now)
    assert stats.vehicles_purged == 1
    remaining_ids = {v.id for v in vehicle_repo.list_all(include_deleted=True)}
    assert old.id not in remaining_ids
    assert recent.id in remaining_ids
    assert not_deleted.id in remaining_ids


def test_cleanup_with_zero_retention_purges_immediately(
    vehicle_repo: InMemoryVehicleRepo,
) -> None:
    seeded = _seed(vehicle_repo)
    soft = SoftDeleteVehicleUseCase(vehicle_repo, InMemorySearchIndex())
    soft.execute(vehicle_id=seeded.id, confirmation="12345")
    cleanup = CleanupDeletedVehiclesUseCase(vehicle_repo, InMemorySearchIndex())
    stats = cleanup.execute(retention_days=0)
    assert stats.vehicles_purged == 1
    assert list(vehicle_repo.list_all(include_deleted=True)) == []


def test_cleanup_skips_non_deleted_vehicles(
    vehicle_repo: InMemoryVehicleRepo,
) -> None:
    _seed(vehicle_repo)
    uc = CleanupDeletedVehiclesUseCase(vehicle_repo, InMemorySearchIndex())
    stats = uc.execute(retention_days=30)
    assert stats.vehicles_purged == 0


def test_cleanup_negative_retention_raises(
    vehicle_repo: InMemoryVehicleRepo,
) -> None:
    uc = CleanupDeletedVehiclesUseCase(vehicle_repo, InMemorySearchIndex())
    with pytest.raises(ValueError):
        uc.execute(retention_days=-1)
