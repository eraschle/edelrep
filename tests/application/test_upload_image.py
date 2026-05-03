from datetime import UTC, datetime

import pytest
from ulid import ULID

from edelrep.application.upload_image import (
    ProcessedImage,
    UploadImageUseCase,
)
from edelrep.domain.entities import ImageSource, Repair, Vehicle
from edelrep.domain.exceptions import RepairNotFound

from .fakes import InMemoryImageRepo, InMemoryRepairRepo


class _StubProcessor:
    def __init__(self, *, captured_at: datetime | None = None) -> None:
        self._captured_at = captured_at

    def process(self, raw_bytes: bytes) -> ProcessedImage:
        return ProcessedImage(
            rotated_bytes=b"ROTATED:" + raw_bytes,
            thumbnail_bytes=b"THUMB:" + raw_bytes,
            captured_at=self._captured_at,
            mime_type="image/jpeg",
        )


def test_upload_returns_persisted_image(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
) -> None:
    repair_repo.save(sample_repair)
    use_case = UploadImageUseCase(repair_repo, image_repo, _StubProcessor())
    image = use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"raw",
        filename="foo.jpg",
    )
    assert image.repair_id == sample_repair.id
    assert image.size_bytes == len(b"ROTATED:raw")
    assert image.storage_key
    assert image_repo.get(image.id).storage_key == image.storage_key


def test_upload_writes_thumbnail_bytes(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_repair: Repair,
) -> None:
    repair_repo.save(sample_repair)
    use_case = UploadImageUseCase(repair_repo, image_repo, _StubProcessor())
    image = use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"raw",
        filename="foo.jpg",
    )
    assert image_repo.thumbnail_bytes_for(image.id) == b"THUMB:raw"


def test_upload_propagates_capture_time(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_repair: Repair,
) -> None:
    repair_repo.save(sample_repair)
    captured = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)
    use_case = UploadImageUseCase(repair_repo, image_repo, _StubProcessor(captured_at=captured))
    image = use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"raw",
        filename="foo.jpg",
    )
    assert image.captured_at == captured


def test_upload_default_source_is_manual(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_repair: Repair,
) -> None:
    repair_repo.save(sample_repair)
    use_case = UploadImageUseCase(repair_repo, image_repo, _StubProcessor())
    image = use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"raw",
        filename="foo.jpg",
    )
    assert image.source == ImageSource.MANUAL


def test_upload_explicit_source(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_repair: Repair,
) -> None:
    repair_repo.save(sample_repair)
    use_case = UploadImageUseCase(repair_repo, image_repo, _StubProcessor())
    image = use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"raw",
        filename="foo.jpg",
        source=ImageSource.EMAIL,
    )
    assert image.source == ImageSource.EMAIL


def test_upload_raises_when_repair_missing(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
) -> None:
    use_case = UploadImageUseCase(repair_repo, image_repo, _StubProcessor())
    with pytest.raises(RepairNotFound):
        use_case.execute(
            repair_id=ULID(),
            raw_bytes=b"raw",
            filename="foo.jpg",
        )
