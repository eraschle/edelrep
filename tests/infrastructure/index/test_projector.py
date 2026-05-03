import shutil
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ulid import ULID

from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.index.projector import (
    ReindexStats,
    SqliteIndexProjector,
)
from edelrep.infrastructure.storage import LocalFilesystemBackend


@pytest.fixture
def storage_repos(
    tmp_path: Path,
) -> tuple[FilesystemVehicleRepository, FilesystemRepairRepository, FilesystemImageRepository, Path]:
    storage_root = tmp_path / "store"
    backend = LocalFilesystemBackend(storage_root)
    return (
        FilesystemVehicleRepository(backend),
        FilesystemRepairRepository(backend),
        FilesystemImageRepository(backend),
        storage_root,
    )


def _vehicle(reg: str = "12345") -> Vehicle:
    return Vehicle(
        id=VehicleId(reg),
        vin=f"VIN-{reg}",
        description=f"Vehicle {reg}",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _repair(vehicle_id: VehicleId, *, day: int = 1) -> Repair:
    return Repair(
        id=ULID(),
        vehicle_id=vehicle_id,
        date=date(2026, 5, day),
        description=f"repair {day}",
        created_at=datetime(2026, 5, day, tzinfo=UTC),
    )


def test_full_rebuild_empty_storage(conn: sqlite3.Connection, storage_repos) -> None:
    vrepo, rrepo, irepo, _ = storage_repos
    projector = SqliteIndexProjector(conn)
    stats = projector.full_rebuild(vrepo, rrepo, irepo)
    assert isinstance(stats, ReindexStats)
    assert stats.vehicles_indexed == 0
    assert stats.repairs_indexed == 0
    assert stats.images_indexed == 0
    cur = conn.execute("SELECT COUNT(*) FROM vehicles")
    assert cur.fetchone()[0] == 0


def test_full_rebuild_indexes_vehicles(conn: sqlite3.Connection, storage_repos) -> None:
    vrepo, rrepo, irepo, _ = storage_repos
    vrepo.save(_vehicle("12345"))
    vrepo.save(_vehicle("67890"))
    projector = SqliteIndexProjector(conn)
    stats = projector.full_rebuild(vrepo, rrepo, irepo)
    assert stats.vehicles_indexed == 2
    cur = conn.execute("SELECT registration_number FROM vehicles ORDER BY registration_number")
    assert [r[0] for r in cur.fetchall()] == ["12345", "67890"]


def test_full_rebuild_indexes_repairs(conn: sqlite3.Connection, storage_repos) -> None:
    vrepo, rrepo, irepo, _ = storage_repos
    v = _vehicle("12345")
    vrepo.save(v)
    rrepo.save(_repair(v.id, day=1))
    rrepo.save(_repair(v.id, day=2))
    projector = SqliteIndexProjector(conn)
    stats = projector.full_rebuild(vrepo, rrepo, irepo)
    assert stats.repairs_indexed == 2
    cur = conn.execute("SELECT COUNT(*) FROM repairs WHERE registration_number = '12345'")
    assert cur.fetchone()[0] == 2


def test_full_rebuild_drops_existing_data(conn: sqlite3.Connection, storage_repos) -> None:
    vrepo, rrepo, irepo, storage_root = storage_repos
    vrepo.save(_vehicle("12345"))
    projector = SqliteIndexProjector(conn)
    projector.full_rebuild(vrepo, rrepo, irepo)
    # Now remove the vehicle file and rebuild — the index row should disappear.
    shutil.rmtree(storage_root / "12345")
    stats = projector.full_rebuild(vrepo, rrepo, irepo)
    assert stats.vehicles_indexed == 0
    cur = conn.execute("SELECT COUNT(*) FROM vehicles")
    assert cur.fetchone()[0] == 0


def test_full_rebuild_records_last_full_reindex_meta(conn: sqlite3.Connection, storage_repos) -> None:
    vrepo, rrepo, irepo, _ = storage_repos
    projector = SqliteIndexProjector(conn)
    projector.full_rebuild(vrepo, rrepo, irepo)
    cur = conn.execute("SELECT value FROM meta WHERE key = 'last_full_reindex'")
    row = cur.fetchone()
    assert row is not None
    parsed = datetime.fromisoformat(row[0])
    assert parsed.tzinfo is not None


def test_upsert_vehicle_individual(conn: sqlite3.Connection) -> None:
    projector = SqliteIndexProjector(conn)
    projector.upsert_vehicle(_vehicle("12345"))
    cur = conn.execute("SELECT registration_number FROM vehicles")
    assert cur.fetchone()[0] == "12345"


def test_remove_vehicle_individual(conn: sqlite3.Connection) -> None:
    projector = SqliteIndexProjector(conn)
    projector.upsert_vehicle(_vehicle("12345"))
    projector.remove_vehicle(VehicleId("12345"))
    cur = conn.execute("SELECT COUNT(*) FROM vehicles")
    assert cur.fetchone()[0] == 0
