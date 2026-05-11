from datetime import UTC, datetime
from pathlib import Path

import pytest
from ulid import ULID

from edelrep.application.update_image_comment import UpdateImageCommentUseCase
from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
from edelrep.domain.exceptions import ImageNotFound
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.storage import LocalFilesystemBackend


def _bootstrap(tmp_path: Path):
    backend = LocalFilesystemBackend(tmp_path)
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
    )
    irepo.save(img, raw_bytes=b"\x00\x00\x00\x00")
    return irepo, img


def test_update_image_comment_sets_comment(tmp_path: Path) -> None:
    irepo, img = _bootstrap(tmp_path)
    use_case = UpdateImageCommentUseCase(irepo)
    use_case.execute(img.id, "added later")
    assert irepo.get(img.id).comment == "added later"


def test_update_image_comment_normalises_whitespace_to_none(tmp_path: Path) -> None:
    irepo, img = _bootstrap(tmp_path)
    use_case = UpdateImageCommentUseCase(irepo)
    use_case.execute(img.id, "   ")
    assert irepo.get(img.id).comment is None


def test_update_image_comment_rejects_too_long(tmp_path: Path) -> None:
    irepo, img = _bootstrap(tmp_path)
    use_case = UpdateImageCommentUseCase(irepo)
    with pytest.raises(ValueError, match="too long"):
        use_case.execute(img.id, "x" * 1001)


def test_update_image_comment_unknown_image_raises(tmp_path: Path) -> None:
    irepo, _ = _bootstrap(tmp_path)
    use_case = UpdateImageCommentUseCase(irepo)
    with pytest.raises(ImageNotFound):
        use_case.execute(ULID(), "x")
