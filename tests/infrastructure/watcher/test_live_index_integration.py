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


def test_empty_index_is_backfilled_from_existing_data_at_start(tmp_path: Path) -> None:
    """A fresh/empty index must be rebuilt from pre-existing filesystem data on start.

    Regression: deleting index.db (or a fresh install / upgrade with existing data)
    left the server showing no vehicles, because the watcher only reacts to *new*
    filesystem events — pre-existing sidecars never got indexed.
    """
    _, vrepo, rrepo, irepo, conn, lock, storage_root = _build_components(tmp_path)
    # Vehicle already exists on disk BEFORE the index is ever built.
    vrepo.save(
        Vehicle(
            id=ULID(),
            registration_number="12345",
            vin="W",
            description="preexisting",
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
        # Immediately after start() — no new FS events fired — the pre-existing
        # vehicle must already be visible in the index (bootstrap, not watcher).
        idx = SqliteSearchIndex(conn, lock)
        results = list(idx.search_vehicles("preexisting"))
        assert results, "empty index was not backfilled from existing data at start"
        assert results[0].registration_number == "12345"
    finally:
        live.stop()
        conn.close()


def test_populated_index_is_not_rebuilt_at_start(tmp_path: Path) -> None:
    """Bootstrap only fires when the index was never fully built.

    A normal restart with an already-populated index must NOT trigger a full
    rebuild (which re-reads the entire photo archive from disk).
    """
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

    class _CountingProjector(SqliteIndexProjector):
        rebuilds = 0

        def full_rebuild(self, *args: object, **kwargs: object):  # type: ignore[override]
            type(self).rebuilds += 1
            return super().full_rebuild(*args, **kwargs)

    # First run: empty index -> one bootstrap rebuild.
    projector = _CountingProjector(conn, lock)
    live = LiveIndex(
        storage_root=storage_root,
        projector=projector,
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        image_repo=irepo,
    )
    live.start()
    live.stop()
    assert _CountingProjector.rebuilds == 1

    # Second run against the now-populated index: no further rebuild.
    live2 = LiveIndex(
        storage_root=storage_root,
        projector=_CountingProjector(conn, lock),
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        image_repo=irepo,
    )
    live2.start()
    try:
        assert _CountingProjector.rebuilds == 1, "populated index must not be rebuilt at start"
    finally:
        live2.stop()
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
