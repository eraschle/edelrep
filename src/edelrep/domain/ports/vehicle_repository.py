from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from edelrep.domain.entities import Vehicle
from edelrep.domain.value_objects import VehicleId


@runtime_checkable
class VehicleRepository(Protocol):
    """Persistence port for :class:`Vehicle` aggregates.

    Concrete implementations live in ``edelrep.infrastructure``.
    """

    def get(self, vehicle_id: VehicleId) -> Vehicle:
        """Return the vehicle or raise :class:`VehicleNotFound`."""
        ...

    def save(self, vehicle: Vehicle) -> None:
        """Insert a new vehicle. Raises :class:`DuplicateVehicle` on collision."""
        ...

    def update(self, vehicle: Vehicle) -> None:
        """Update an existing vehicle. Raises :class:`VehicleNotFound` if absent."""
        ...

    def list_all(self) -> Iterable[Vehicle]:
        """Iterate over all known vehicles in unspecified order."""
        ...

    def exists(self, vehicle_id: VehicleId) -> bool:
        """Return whether a vehicle with this id is stored."""
        ...
