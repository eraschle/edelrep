import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from ulid import ULID

from edelrep.domain.entities import Vehicle
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.index import (
    SqliteIndexProjector,
    SqliteSearchIndex,
    open_index_database,
)
from edelrep.infrastructure.storage import LocalFilesystemBackend
from edelrep.infrastructure.watcher.live_index import LiveIndex

WATCH_DEADLINE_SECONDS = 10.0


def _build_components(
    tmp_path: Path,
) -> tuple[
    LocalFilesystemBackend,
    FilesystemVehicleRepository,
    FilesystemRepairRepository,
    FilesystemImageRepository,
    sqlite3.Connection,
    threading.RLock,
    Path,
]:
    storage = tmp_path / "store"
    storage.mkdir()
    backend = LocalFilesystemBackend(storage)
    vrepo = FilesystemVehicleRepository(backend)
    rrepo = FilesystemRepairRepository(backend)
    irepo = FilesystemImageRepository(backend)
    conn, lock = open_index_database(tmp_path / "index.db")
    return backend, vrepo, rrepo, irepo, conn, lock, storage


def test_external_vehicle_appears_in_search_within_sla(tmp_path: Path) -> None:
    _, vrepo, rrepo, irepo, conn, lock, storage_root = _build_components(tmp_path)
    projector = SqliteIndexProjector(conn, lock)
    live = LiveIndex(
        storage_root=storage_root,
        projector=projector,
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        image_repo=irepo,
        debounce_seconds=0.2,
    )
    live.start()
    try:
        vrepo.save(
            Vehicle(
                id=ULID(),
                registration_number="12345",
                vin="W",
                description="liveindex",
                created_at=datetime(2026, 5, 3, tzinfo=UTC),
            )
        )
        deadline = time.monotonic() + WATCH_DEADLINE_SECONDS
        idx = SqliteSearchIndex(conn, lock)
        results: list[Vehicle] = []
        while time.monotonic() < deadline:
            results = list(idx.search_vehicles("liveindex"))
            if results:
                break
            time.sleep(0.1)
        assert results, f"Watcher did not propagate vehicle within {WATCH_DEADLINE_SECONDS}s"
        assert results[0].registration_number == "12345"
    finally:
        live.stop()
        conn.close()


def test_drift_detected_at_start_when_sidecar_newer_than_index(tmp_path: Path) -> None:
    _, vrepo, rrepo, irepo, conn, lock, storage_root = _build_components(tmp_path)
    vrepo.save(
        Vehicle(
            id=ULID(),
            registration_number="12345",
            vin="W",
            description="x",
            created_at=datetime(2026, 5, 3, tzinfo=UTC),
        )
    )
    live = LiveIndex(
        storage_root=storage_root,
        projector=SqliteIndexProjector(conn, lock),
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        image_repo=irepo,
    )
    live.start()
    try:
        assert live.drift_detected is True
    finally:
        live.stop()
        conn.close()


def test_stop_is_idempotent(tmp_path: Path) -> None:
    _, vrepo, rrepo, irepo, conn, lock, storage_root = _build_components(tmp_path)
    live = LiveIndex(
        storage_root=storage_root,
        projector=SqliteIndexProjector(conn, lock),
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        image_repo=irepo,
    )
    live.start()
    live.stop()
    live.stop()  # second stop should be no-op
    conn.close()


def test_is_running(tmp_path: Path) -> None:
    _, vrepo, rrepo, irepo, conn, lock, storage_root = _build_components(tmp_path)
    live = LiveIndex(
        storage_root=storage_root,
        projector=SqliteIndexProjector(conn, lock),
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        image_repo=irepo,
    )
    assert not live.is_running()
    live.start()
    assert live.is_running()
    live.stop()
    assert not live.is_running()
    conn.close()
