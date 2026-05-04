import io
from datetime import UTC, date, datetime
from pathlib import Path

from PIL import Image as PILImage
from ulid import ULID

from edelrep.application.upload_image import UploadImageUseCase
from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.exif.pillow_processor import PillowImageProcessor
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.storage import LocalFilesystemBackend


def _real_jpeg_bytes() -> bytes:
    img = PILImage.new("RGB", (640, 480), color=(10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_upload_creates_correct_layout(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path / "store")
    vrepo = FilesystemVehicleRepository(backend)
    rrepo = FilesystemRepairRepository(backend)
    irepo = FilesystemImageRepository(backend)

    vrepo.save(
        Vehicle(
            id=VehicleId("12345"),
            vin="W",
            description="x",
            created_at=datetime(2026, 5, 3, tzinfo=UTC),
        )
    )

    repair = Repair(
        id=ULID(),
        vehicle_id=VehicleId("12345"),
        date=date(2026, 5, 3),
        description="brakes",
        created_at=datetime(2026, 5, 3, tzinfo=UTC),
    )
    rrepo.save(repair)

    use_case = UploadImageUseCase(rrepo, irepo, PillowImageProcessor(), backend)
    image = use_case.execute(
        repair_id=repair.id,
        raw_bytes=_real_jpeg_bytes(),
        filename="my-photo.jpg",
    )

    # Verify filesystem layout per PLAN.md §6.
    repair_dir = tmp_path / "store" / "12345" / "2026-05-03__brakes"
    assert repair_dir.is_dir()
    image_files = sorted(p.name for p in repair_dir.iterdir() if p.is_file())
    assert any(name.startswith("0001_") and name.endswith(".jpg") for name in image_files)
    thumb_dir = repair_dir / "_thumbs"
    assert thumb_dir.is_dir()
    thumbs = list(thumb_dir.iterdir())
    assert len(thumbs) == 1
    # The returned image's storage_key matches the actual key.
    assert backend.exists(image.storage_key)
    assert image.thumbnail_key is not None
    assert backend.exists(image.thumbnail_key)
