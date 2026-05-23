from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from ulid import ULID

from edelrep.domain.entities import Vehicle


@runtime_checkable
class VehicleRepository(Protocol):
    """Persistence port for :class:`Vehicle` aggregates.

    Concrete implementations live in ``edelrep.infrastructure``.
    """

    def get(self, vehicle_id: ULID) -> Vehicle:
        """Return the vehicle or raise :class:`VehicleNotFound`."""
        ...

    def save(self, vehicle: Vehicle) -> None:
        """Insert a new vehicle.

        Raises :class:`DuplicateRegistrationNumber` if the Stammnummer is
        already used by another vehicle, or :class:`DuplicateVin` if the
        Rahmennummer collides.
        """
        ...

    def update(self, vehicle: Vehicle) -> None:
        """Update an existing vehicle. Raises :class:`VehicleNotFound` if absent."""
        ...

    def list_all(self) -> Iterable[Vehicle]:
        """Iterate over all known vehicles in unspecified order."""
        ...

    def exists(self, vehicle_id: ULID) -> bool:
        """Return whether a vehicle with this id is stored."""
        ...

    def find_by_registration(self, registration_number: str) -> Vehicle | None:
        """Look up a vehicle by Stammnummer; ``None`` if no match."""
        ...

    def find_by_vin(self, vin: str) -> Vehicle | None:
        """Look up a vehicle by Rahmennummer; ``None`` if no match."""
        ...
