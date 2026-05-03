from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ulid import ULID

from edelrep.domain.entities import Image, ImageSource
from edelrep.domain.ports import ImageRepository, RepairRepository


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    rotated_bytes: bytes
    thumbnail_bytes: bytes
    captured_at: datetime | None
    mime_type: str


class ImageProcessor(Protocol):
    def process(self, raw_bytes: bytes) -> ProcessedImage: ...


class UploadImageUseCase:
    """Persist a new image: validate repair -> process bytes -> store entity + bytes."""

    def __init__(
        self,
        repair_repo: RepairRepository,
        image_repo: ImageRepository,
        processor: ImageProcessor,
    ) -> None:
        self._repair_repo = repair_repo
        self._image_repo = image_repo
        self._processor = processor

    def execute(
        self,
        *,
        repair_id: ULID,
        raw_bytes: bytes,
        filename: str,
        source: ImageSource = ImageSource.MANUAL,
    ) -> Image:
        # Raises RepairNotFound if the repair doesn't exist.
        self._repair_repo.get(repair_id)

        processed = self._processor.process(raw_bytes)

        image = Image(
            id=ULID(),
            repair_id=repair_id,
            storage_key="",  # populated by the repository on save/get
            thumbnail_key=None,
            filename=filename,
            mime_type=processed.mime_type,
            size_bytes=len(processed.rotated_bytes),
            source=source,
            uploaded_at=datetime.now(UTC),
            captured_at=processed.captured_at,
        )

        self._image_repo.save(
            image,
            raw_bytes=processed.rotated_bytes,
            thumbnail_bytes=processed.thumbnail_bytes,
        )
        return self._image_repo.get(image.id)
