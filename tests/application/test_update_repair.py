from datetime import UTC, date, datetime

import pytest
from ulid import ULID

from edelrep.application.update_repair import UpdateRepairUseCase
from edelrep.domain.entities import Repair
from edelrep.domain.exceptions import RepairNotFound
from tests.application.fakes import InMemoryRepairRepo


def _seed_repair(repo: InMemoryRepairRepo) -> Repair:
    repair = Repair(
        id=ULID(),
        vehicle_id=ULID(),
        date=date(2026, 5, 3),
        description="alt",
        created_at=datetime(2026, 5, 3, tzinfo=UTC),
    )
    repo.save(repair)
    return repair


def test_update_repair_changes_description_and_keeps_identity() -> None:
    repo = InMemoryRepairRepo()
    original = _seed_repair(repo)

    updated = UpdateRepairUseCase(repo).execute(repair_id=original.id, description="neu")

    assert updated.description == "neu"
    assert updated.id == original.id
    assert updated.vehicle_id == original.vehicle_id
    assert updated.date == original.date
    assert updated.created_at == original.created_at
    assert repo.get(original.id).description == "neu"


def test_update_repair_blank_description_becomes_none() -> None:
    repo = InMemoryRepairRepo()
    original = _seed_repair(repo)

    updated = UpdateRepairUseCase(repo).execute(repair_id=original.id, description="   ")

    assert updated.description is None


def test_update_repair_unknown_id_raises() -> None:
    with pytest.raises(RepairNotFound):
        UpdateRepairUseCase(InMemoryRepairRepo()).execute(repair_id=ULID(), description="x")
