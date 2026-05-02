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

    def save(self, image: Image) -> None:
        """Insert a new image record."""
        ...

    def list_for_repair(self, repair_id: ULID) -> Iterable[Image]:
        """Iterate the repair's images in upload order."""
        ...
