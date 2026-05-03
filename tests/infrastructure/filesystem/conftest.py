from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import fsspec
import pytest
from fsspec.implementations.memory import MemoryFileSystem
from ulid import ULID

from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
from edelrep.domain.ports import StorageBackend
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.storage import FsspecBackend, LocalFilesystemBackend


@pytest.fixture
def storage_root(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path / "storage"
    root.mkdir()
    yield root


@pytest.fixture(params=["local", "memory"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> StorageBackend:
    if request.param == "local":
        return LocalFilesystemBackend(tmp_path / "store")
    fs = fsspec.filesystem("memory")
    if isinstance(fs, MemoryFileSystem):
        fs.store.clear()
        fs.pseudo_dirs.clear()
    safe = request.node.nodeid.replace("/", "__").replace("::", "__").replace("[", "_").replace("]", "_")
    return FsspecBackend(fs, root=f"/edelrep-test-{safe}")


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


@pytest.fixture
def sample_image_bytes() -> bytes:
    # Minimal JPEG SOI/EOI markers + padding. Content is irrelevant for these tests.
    return b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"


def make_image(repair_id: ULID, *, image_id: ULID | None = None) -> Image:
    iid = image_id or ULID()
    return Image(
        id=iid,
        repair_id=repair_id,
        storage_key="placeholder",
        thumbnail_key=None,
        filename=f"0001_{iid!s}.jpg",
        mime_type="image/jpeg",
        size_bytes=72,
        source=ImageSource.MANUAL,
        uploaded_at=datetime(2026, 4, 15, 16, 35, tzinfo=UTC),
        captured_at=None,
    )
