from ulid import ULID

from edelrep.domain.entities import Image
from edelrep.domain.ports import ImageRepository, StorageBackend


class GetImageUseCase:
    """Fetch an image entity and its raw bytes for download."""

    def __init__(self, image_repo: ImageRepository, backend: StorageBackend) -> None:
        self._image_repo = image_repo
        self._backend = backend

    def execute(self, image_id: ULID) -> tuple[Image, bytes]:
        image = self._image_repo.get(image_id)
        return image, self._backend.read_bytes(image.storage_key)
