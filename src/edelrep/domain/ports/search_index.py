from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from ulid import ULID

from edelrep.domain.entities import Vehicle


@runtime_checkable
class SearchIndex(Protocol):
    """Read/write port for the (rebuildable) index cache.

    The index is never the source of truth — it must be reproducible from
    the filesystem. Mutating methods are idempotent.
    """

    def search_vehicles(self, query: str, limit: int = 20) -> Iterable[Vehicle]:
        """Full-text search over registration_number, vin, description."""
        ...

    def list_vehicles_by_activity(self, limit: int) -> Iterable[Vehicle]:
        """Iterate vehicles, most-recently-active first.

        Activity is the maximum of (most recent repair, most recent image
        upload, vehicle.created_at). Implementations decide how they
        materialise this ranking.
        """
        ...

    def upsert_vehicle(self, vehicle: Vehicle) -> None:
        """Insert or update the index row for ``vehicle``."""
        ...

    def remove_vehicle(self, vehicle_id: ULID) -> None:
        """Drop the index row. No-op if absent."""
        ...

    def remove_image(self, image_id: ULID) -> None:
        """Drop the index row for a single image. No-op if absent."""
        ...

    def clear(self) -> None:
        """Drop all rows. Used before a full reindex."""
        ...
