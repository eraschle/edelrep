import sqlite3
from datetime import UTC, date, datetime

import pytest
from ulid import ULID

from edelrep.application.reindex import ReindexUseCase
from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.index.connection import open_index_database
from edelrep.infrastructure.index.projector import (
    ReindexStats,
    SqliteIndexProjector,
)

from .fakes import InMemoryImageRepo, InMemoryRepairRepo, InMemoryVehicleRepo


@pytest.fixture
def conn() -> sqlite3.Connection:
    return open_index_database(":memory:")


def test_reindex_returns_stats(
    conn: sqlite3.Connection,
    vehicle_repo: InMemoryVehicleRepo,
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
) -> None:
    vehicle = Vehicle(
        id=VehicleId("12345"),
        vin="X",
        description="x",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    vehicle_repo.save(vehicle)
    repair_repo.save(
        Repair(
            id=ULID(),
            vehicle_id=vehicle.id,
            date=date(2026, 5, 1),
            description="brakes",
            created_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
    )
    projector = SqliteIndexProjector(conn)
    use_case = ReindexUseCase(projector, vehicle_repo, repair_repo, image_repo)
    stats = use_case.execute()
    assert isinstance(stats, ReindexStats)
    assert stats.vehicles_indexed == 1
    assert stats.repairs_indexed == 1


def test_reindex_empty_storage(
    conn: sqlite3.Connection,
    vehicle_repo: InMemoryVehicleRepo,
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
) -> None:
    projector = SqliteIndexProjector(conn)
    use_case = ReindexUseCase(projector, vehicle_repo, repair_repo, image_repo)
    stats = use_case.execute()
    assert stats.vehicles_indexed == 0
