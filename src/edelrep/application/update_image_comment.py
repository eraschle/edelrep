from ulid import ULID

from edelrep.domain.entities import Image
from edelrep.domain.ports import ImageRepository


class UpdateImageCommentUseCase:
    """Set or clear the comment on an existing image."""

    def __init__(self, image_repo: ImageRepository) -> None:
        self._image_repo = image_repo

    def execute(self, image_id: ULID, comment: str | None) -> Image:
        normalised = (comment.strip() if comment else None) or None
        if normalised is not None and len(normalised) > 1000:
            raise ValueError("comment too long (max 1000 chars)")
        self._image_repo.update_comment(image_id, normalised)
        return self._image_repo.get(image_id)
