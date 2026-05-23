from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from ulid import ULID

from edelrep.domain.entities import Vehicle


@runtime_checkable
class VehicleRepository(Protocol):
    """Persistence port for :class:`Vehicle` aggregates.

    Concrete implementations live in ``edelrep.infrastructure``. Soft-deleted
    vehicles are hidden from the default read methods (`get`, `list_all`,
    `find_by_*`); callers that need to enumerate them — for example the
    cleanup job — must pass ``include_deleted=True``.
    """

    def get(self, vehicle_id: ULID, *, include_deleted: bool = False) -> Vehicle:
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

    def hard_delete(self, vehicle_id: ULID) -> None:
        """Permanently remove the vehicle and everything stored under it."""
        ...

    def list_all(self, *, include_deleted: bool = False) -> Iterable[Vehicle]:
        """Iterate over all known vehicles in unspecified order."""
        ...

    def exists(self, vehicle_id: ULID, *, include_deleted: bool = False) -> bool:
        """Return whether a vehicle with this id is stored."""
        ...

    def find_by_registration(self, registration_number: str) -> Vehicle | None:
        """Look up a non-deleted vehicle by Stammnummer; ``None`` if no match."""
        ...

    def find_by_vin(self, vin: str) -> Vehicle | None:
        """Look up a non-deleted vehicle by Rahmennummer; ``None`` if no match."""
        ...
