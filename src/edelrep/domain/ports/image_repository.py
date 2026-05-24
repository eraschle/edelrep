from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from ulid import ULID

from edelrep.domain.entities import Image


@runtime_checkable
class ImageRepository(Protocol):
    """Persistence port for :class:`Image` records."""

    def get(self, image_id: ULID) -> Image:
        """Return the image or raise :class:`ImageNotFound`."""
        ...

    def save(
        self,
        image: Image,
        *,
        raw_bytes: bytes,
        thumbnail_bytes: bytes | None = None,
    ) -> None:
        """Persist the image record together with the raw image bytes
        (and optional thumbnail). The implementation is responsible for
        writing both byte streams atomically. If ``image.comment`` is
        non-``None`` the implementation must also persist it."""
        ...

    def list_for_repair(self, repair_id: ULID) -> Iterable[Image]:
        """Iterate the repair's images in upload order."""
        ...

    def update_comment(self, image_id: ULID, comment: str | None) -> None:
        """Set or clear the comment for an existing image.

        ``None`` removes any persisted comment. Raises
        :class:`ImageNotFound` when the image does not exist.
        """
        ...

    def delete(self, image_id: ULID) -> None:
        """Hard-delete the image, its thumbnail and the per-image sidecar.

        Raises :class:`ImageNotFound` if the image does not exist.
        """
        ...
