import time
from datetime import UTC, datetime
from pathlib import Path

from ulid import ULID

from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.index import SqliteIndexProjector, open_index_database
from edelrep.infrastructure.storage import LocalFilesystemBackend
from edelrep.infrastructure.watcher.key_mapper import EntityKind, classify
from edelrep.infrastructure.watcher.live_index import LiveIndex


def test_classify_image_sidecar_returns_image_sidecar() -> None:
    key = "12345/2026-05-10__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.json"
    assert classify(key) is EntityKind.IMAGE_SIDECAR


def test_live_index_keeps_image_indexed_on_sidecar_write(tmp_path: Path) -> None:
    storage = tmp_path / "store"
    storage.mkdir()
    backend = LocalFilesystemBackend(storage)
    vrepo = FilesystemVehicleRepository(backend)
    rrepo = FilesystemRepairRepository(backend)
    irepo = FilesystemImageRepository(backend)

    vehicle = Vehicle(id=VehicleId("12345"), vin=None, description=None, created_at=datetime.now(UTC))
    vrepo.save(vehicle)
    repair = Repair(
        id=ULID(),
        vehicle_id=vehicle.id,
        date=datetime.now(UTC).date(),
        description="brakes",
        created_at=datetime.now(UTC),
    )
    rrepo.save(repair)
    img = Image(
        id=ULID(),
        repair_id=repair.id,
        storage_key="",
        thumbnail_key=None,
        filename="x.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime.now(UTC),
        captured_at=None,
        comment=None,
    )
    irepo.save(img, raw_bytes=b"\x00\x00\x00\x00")

    conn, lock = open_index_database(tmp_path / "index.db")
    projector = SqliteIndexProjector(conn, lock)
    live = LiveIndex(
        storage_root=storage,
        projector=projector,
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        image_repo=irepo,
        debounce_seconds=0.05,
    )
    live.start()
    try:
        irepo.update_comment(img.id, "a comment")
        time.sleep(0.4)  # 50ms debounce + slack for FS event propagation
        cur = conn.execute("SELECT COUNT(*) FROM images WHERE id = ?", (str(img.id),))
        assert cur.fetchone()[0] == 1
    finally:
        live.stop()
        conn.close()
