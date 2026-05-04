import shutil
import sqlite3
import threading
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ulid import ULID

from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
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


def test_full_rebuild_empty_storage(conn: sqlite3.Connection, lock: threading.RLock, storage_repos) -> None:
    vrepo, rrepo, irepo, _ = storage_repos
    projector = SqliteIndexProjector(conn, lock)
    stats = projector.full_rebuild(vrepo, rrepo, irepo)
    assert isinstance(stats, ReindexStats)
    assert stats.vehicles_indexed == 0
    assert stats.repairs_indexed == 0
    assert stats.images_indexed == 0
    cur = conn.execute("SELECT COUNT(*) FROM vehicles")
    assert cur.fetchone()[0] == 0


def test_full_rebuild_indexes_vehicles(
    conn: sqlite3.Connection, lock: threading.RLock, storage_repos
) -> None:
    vrepo, rrepo, irepo, _ = storage_repos
    vrepo.save(_vehicle("12345"))
    vrepo.save(_vehicle("67890"))
    projector = SqliteIndexProjector(conn, lock)
    stats = projector.full_rebuild(vrepo, rrepo, irepo)
    assert stats.vehicles_indexed == 2
    cur = conn.execute("SELECT registration_number FROM vehicles ORDER BY registration_number")
    assert [r[0] for r in cur.fetchall()] == ["12345", "67890"]


def test_full_rebuild_indexes_repairs(conn: sqlite3.Connection, lock: threading.RLock, storage_repos) -> None:
    vrepo, rrepo, irepo, _ = storage_repos
    v = _vehicle("12345")
    vrepo.save(v)
    rrepo.save(_repair(v.id, day=1))
    rrepo.save(_repair(v.id, day=2))
    projector = SqliteIndexProjector(conn, lock)
    stats = projector.full_rebuild(vrepo, rrepo, irepo)
    assert stats.repairs_indexed == 2
    cur = conn.execute("SELECT COUNT(*) FROM repairs WHERE registration_number = '12345'")
    assert cur.fetchone()[0] == 2


def test_full_rebuild_drops_existing_data(
    conn: sqlite3.Connection, lock: threading.RLock, storage_repos
) -> None:
    vrepo, rrepo, irepo, storage_root = storage_repos
    vrepo.save(_vehicle("12345"))
    projector = SqliteIndexProjector(conn, lock)
    projector.full_rebuild(vrepo, rrepo, irepo)
    # Now remove the vehicle file and rebuild — the index row should disappear.
    shutil.rmtree(storage_root / "12345")
    stats = projector.full_rebuild(vrepo, rrepo, irepo)
    assert stats.vehicles_indexed == 0
    cur = conn.execute("SELECT COUNT(*) FROM vehicles")
    assert cur.fetchone()[0] == 0


def test_full_rebuild_records_last_full_reindex_meta(
    conn: sqlite3.Connection, lock: threading.RLock, storage_repos
) -> None:
    vrepo, rrepo, irepo, _ = storage_repos
    projector = SqliteIndexProjector(conn, lock)
    projector.full_rebuild(vrepo, rrepo, irepo)
    cur = conn.execute("SELECT value FROM meta WHERE key = 'last_full_reindex'")
    row = cur.fetchone()
    assert row is not None
    parsed = datetime.fromisoformat(row[0])
    assert parsed.tzinfo is not None


def test_upsert_vehicle_individual(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    projector = SqliteIndexProjector(conn, lock)
    projector.upsert_vehicle(_vehicle("12345"))
    cur = conn.execute("SELECT registration_number FROM vehicles")
    assert cur.fetchone()[0] == "12345"


def test_remove_vehicle_individual(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    projector = SqliteIndexProjector(conn, lock)
    projector.upsert_vehicle(_vehicle("12345"))
    projector.remove_vehicle(VehicleId("12345"))
    cur = conn.execute("SELECT COUNT(*) FROM vehicles")
    assert cur.fetchone()[0] == 0


def _image(repair_id: ULID, *, captured_at: datetime | None = None) -> Image:
    return Image(
        id=ULID(),
        repair_id=repair_id,
        storage_key="placeholder/0001.jpg",
        thumbnail_key=None,
        filename="0001.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime(2026, 5, 1, tzinfo=UTC),
        captured_at=captured_at,
    )


def test_upsert_repair_individual(conn: sqlite3.Connection, lock: threading.RLock, storage_repos) -> None:
    vrepo, _, _, _ = storage_repos
    v = _vehicle("12345")
    vrepo.save(v)
    projector = SqliteIndexProjector(conn, lock)
    projector.upsert_vehicle(v)
    repair = _repair(v.id, day=1)
    projector.upsert_repair(repair)
    cur = conn.execute("SELECT COUNT(*) FROM repairs WHERE id = ?", (str(repair.id),))
    assert cur.fetchone()[0] == 1


def test_upsert_image_individual(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    projector = SqliteIndexProjector(conn, lock)
    repair_id = ULID()
    img = _image(repair_id, captured_at=datetime(2026, 4, 15, tzinfo=UTC))
    projector.upsert_image(img)
    cur = conn.execute("SELECT exif_taken_at FROM images WHERE id = ?", (str(img.id),))
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "2026-04-15T00:00:00+00:00"


def test_upsert_image_with_no_captured_at(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    projector = SqliteIndexProjector(conn, lock)
    repair_id = ULID()
    img = _image(repair_id, captured_at=None)
    projector.upsert_image(img)
    cur = conn.execute("SELECT exif_taken_at FROM images WHERE id = ?", (str(img.id),))
    row = cur.fetchone()
    assert row[0] is None


def test_remove_repair_individual(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    projector = SqliteIndexProjector(conn, lock)
    repair_id = ULID()
    repair = Repair(
        id=repair_id,
        vehicle_id=VehicleId("12345"),
        date=date(2026, 5, 1),
        description="x",
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    projector.upsert_repair(repair)
    projector.remove_repair(repair_id)
    cur = conn.execute("SELECT COUNT(*) FROM repairs")
    assert cur.fetchone()[0] == 0


def test_remove_image_individual(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    projector = SqliteIndexProjector(conn, lock)
    img = _image(ULID())
    projector.upsert_image(img)
    projector.remove_image(img.id)
    cur = conn.execute("SELECT COUNT(*) FROM images")
    assert cur.fetchone()[0] == 0


def test_full_rebuild_indexes_images(conn: sqlite3.Connection, lock: threading.RLock, storage_repos) -> None:
    vrepo, rrepo, irepo, _ = storage_repos
    v = _vehicle("12345")
    vrepo.save(v)
    repair = _repair(v.id, day=1)
    rrepo.save(repair)
    irepo.save(
        _image(repair.id),
        raw_bytes=b"\xff\xd8\xff\xd9",
        thumbnail_bytes=b"\xff\xd8\xff\xd9",
    )
    projector = SqliteIndexProjector(conn, lock)
    stats = projector.full_rebuild(vrepo, rrepo, irepo)
    assert stats.images_indexed == 1
    cur = conn.execute("SELECT COUNT(*) FROM images")
    assert cur.fetchone()[0] == 1
