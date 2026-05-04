import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from ulid import ULID

from edelrep.domain.entities import Image, ImageSource
from edelrep.domain.exceptions import DuplicateImage
from edelrep.domain.ports import ImageRepository, RepairRepository, StorageBackend


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    rotated_bytes: bytes
    thumbnail_bytes: bytes
    captured_at: datetime | None
    mime_type: str


@runtime_checkable
class ImageProcessor(Protocol):
    def process(self, raw_bytes: bytes) -> ProcessedImage: ...


class UploadImageUseCase:
    """Persist a new image: validate repair -> process bytes -> store entity + bytes."""

    def __init__(
        self,
        repair_repo: RepairRepository,
        image_repo: ImageRepository,
        processor: ImageProcessor,
        backend: StorageBackend,
    ) -> None:
        self._repair_repo = repair_repo
        self._image_repo = image_repo
        self._processor = processor
        self._backend = backend

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

        # Duplicate-check on processed bytes (what would be stored on disk).
        incoming_size = len(processed.rotated_bytes)
        incoming_hash = hashlib.sha256(processed.rotated_bytes).digest()
        for existing in self._image_repo.list_for_repair(repair_id):
            if existing.size_bytes != incoming_size:
                continue
            existing_raw = self._backend.read_bytes(existing.storage_key)
            if hashlib.sha256(existing_raw).digest() == incoming_hash:
                raise DuplicateImage(repair_id=repair_id, existing_filename=existing.filename)

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
