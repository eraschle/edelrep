from datetime import UTC, datetime

import pytest
from ulid import ULID

from edelrep.application.upload_image import (
    ProcessedImage,
    UploadImageUseCase,
)
from edelrep.domain.entities import ImageSource, Repair, Vehicle
from edelrep.domain.exceptions import DuplicateImage, RepairNotFound

from .fakes import InMemoryImageRepo, InMemoryRepairRepo, InMemoryStorageBackend


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


def _make_use_case(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    processor: _StubProcessor | None = None,
) -> UploadImageUseCase:
    return UploadImageUseCase(
        repair_repo,
        image_repo,
        processor or _StubProcessor(),
        InMemoryStorageBackend(image_repo),
    )


def test_upload_returns_persisted_image(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
) -> None:
    repair_repo.save(sample_repair)
    use_case = _make_use_case(repair_repo, image_repo)
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
    use_case = _make_use_case(repair_repo, image_repo)
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
    use_case = _make_use_case(repair_repo, image_repo, _StubProcessor(captured_at=captured))
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
    use_case = _make_use_case(repair_repo, image_repo)
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
    use_case = _make_use_case(repair_repo, image_repo)
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
    use_case = _make_use_case(repair_repo, image_repo)
    with pytest.raises(RepairNotFound):
        use_case.execute(
            repair_id=ULID(),
            raw_bytes=b"raw",
            filename="foo.jpg",
        )


def test_upload_duplicate_image_raises_duplicate_image(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_repair: Repair,
) -> None:
    """Uploading the same raw_bytes twice raises DuplicateImage on the second call."""
    repair_repo.save(sample_repair)
    use_case = _make_use_case(repair_repo, image_repo)

    # First upload succeeds.
    use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"identical-content",
        filename="photo.jpg",
    )

    # Second upload with the same bytes (even a different filename) must raise.
    with pytest.raises(DuplicateImage) as exc_info:
        use_case.execute(
            repair_id=sample_repair.id,
            raw_bytes=b"identical-content",
            filename="copy.jpg",
        )

    assert exc_info.value.repair_id == sample_repair.id
    assert exc_info.value.existing_filename == "photo.jpg"

    # Only one image should exist for this repair.
    stored = list(image_repo.list_for_repair(sample_repair.id))
    assert len(stored) == 1


def test_upload_different_images_both_succeed(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_repair: Repair,
) -> None:
    """Uploading two genuinely different images must not trigger DuplicateImage."""
    repair_repo.save(sample_repair)
    use_case = _make_use_case(repair_repo, image_repo)

    use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"image-A",
        filename="a.jpg",
    )
    use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"image-B",
        filename="b.jpg",
    )

    stored = list(image_repo.list_for_repair(sample_repair.id))
    assert len(stored) == 2


def test_upload_image_with_comment_persists_comment(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_repair: Repair,
) -> None:
    repair_repo.save(sample_repair)
    use_case = _make_use_case(repair_repo, image_repo)
    image = use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"raw",
        filename="foo.jpg",
        comment="brakes left front",
    )
    assert image.comment == "brakes left front"
    assert image_repo.get(image.id).comment == "brakes left front"


def test_upload_image_normalises_whitespace_only_comment_to_none(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_repair: Repair,
) -> None:
    repair_repo.save(sample_repair)
    use_case = _make_use_case(repair_repo, image_repo)
    image = use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"raw",
        filename="foo.jpg",
        comment="   ",
    )
    assert image.comment is None
