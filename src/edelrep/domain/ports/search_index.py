from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from edelrep.domain.entities import Vehicle
from edelrep.domain.value_objects import VehicleId


@runtime_checkable
class SearchIndex(Protocol):
    """Read/write port for the (rebuildable) index cache.

    The index is never the source of truth — it must be reproducible from
    the filesystem. Mutating methods are idempotent.
    """

    def search_vehicles(self, query: str, limit: int = 20) -> Iterable[Vehicle]:
        """Full-text search over registration_number, vin, description."""
        ...

    def upsert_vehicle(self, vehicle: Vehicle) -> None:
        """Insert or update the index row for ``vehicle``."""
        ...

    def remove_vehicle(self, vehicle_id: VehicleId) -> None:
        """Drop the index row. No-op if absent."""
        ...

    def clear(self) -> None:
        """Drop all rows. Used before a full reindex."""
        ...
