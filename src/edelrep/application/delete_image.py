from ulid import ULID

from edelrep.domain.ports import ImageRepository, SearchIndex


class DeleteImageUseCase:
    """Hard-delete a single repair image, thumbnail, sidecar and index row."""

    def __init__(
        self,
        image_repo: ImageRepository,
        search_index: SearchIndex,
    ) -> None:
        self._image_repo = image_repo
        self._search_index = search_index

    def execute(self, image_id: ULID) -> None:
        # Resolve first so a missing image surfaces ImageNotFound to callers
        # before any filesystem mutation runs.
        self._image_repo.get(image_id)
        self._image_repo.delete(image_id)
        self._search_index.remove_image(image_id)
