from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from ulid import ULID

from edelrep.domain.entities import Repair


@runtime_checkable
class RepairRepository(Protocol):
    """Persistence port for :class:`Repair` aggregates."""

    def get(self, repair_id: ULID) -> Repair:
        """Return the repair or raise :class:`RepairNotFound`."""
        ...

    def save(self, repair: Repair) -> None:
        """Insert a new repair record."""
        ...

    def update(self, repair: Repair) -> None:
        """Update an existing repair. Raises :class:`RepairNotFound` if absent."""
        ...

    def list_for_vehicle(self, vehicle_id: ULID) -> Iterable[Repair]:
        """Iterate the vehicle's repairs, newest first."""
        ...
