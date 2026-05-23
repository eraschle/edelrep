from dataclasses import dataclass, replace
from datetime import UTC, datetime

from ulid import ULID

from edelrep.domain.entities import Vehicle
from edelrep.domain.exceptions import DeletionConfirmationMismatch
from edelrep.domain.ports import SearchIndex, VehicleRepository


def _candidate_confirmations(vehicle: Vehicle) -> set[str]:
    """Strings that count as a valid confirmation for this vehicle."""
    candidates: set[str] = {str(vehicle.id)}
    if vehicle.registration_number:
        candidates.add(vehicle.registration_number)
    if vehicle.vin:
        candidates.add(vehicle.vin)
    return candidates


class SoftDeleteVehicleUseCase:
    """Mark a vehicle as deleted after the user re-types its key as confirmation."""

    def __init__(
        self,
        vehicle_repo: VehicleRepository,
        search_index: SearchIndex,
    ) -> None:
        self._vehicle_repo = vehicle_repo
        self._search_index = search_index

    def execute(self, *, vehicle_id: ULID, confirmation: str) -> Vehicle:
        vehicle = self._vehicle_repo.get(vehicle_id)
        if confirmation.strip() not in _candidate_confirmations(vehicle):
            raise DeletionConfirmationMismatch
        deleted = replace(vehicle, deleted_at=datetime.now(UTC))
        self._vehicle_repo.update(deleted)
        self._search_index.remove_vehicle(deleted.id)
        return deleted


@dataclass(frozen=True, slots=True)
class CleanupStats:
    vehicles_purged: int


class CleanupDeletedVehiclesUseCase:
    """Hard-delete soft-deleted vehicles that exceeded the retention window."""

    DEFAULT_RETENTION_DAYS = 30

    def __init__(
        self,
        vehicle_repo: VehicleRepository,
        search_index: SearchIndex,
    ) -> None:
        self._vehicle_repo = vehicle_repo
        self._search_index = search_index

    def execute(
        self,
        *,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        now: datetime | None = None,
    ) -> CleanupStats:
        if retention_days < 0:
            raise ValueError("retention_days must be non-negative")
        reference = now or datetime.now(UTC)
        threshold_seconds = retention_days * 86400
        purged = 0
        for vehicle in list(self._vehicle_repo.list_all(include_deleted=True)):
            if vehicle.deleted_at is None:
                continue
            age_seconds = (reference - vehicle.deleted_at).total_seconds()
            if age_seconds < threshold_seconds:
                continue
            self._vehicle_repo.hard_delete(vehicle.id)
            self._search_index.remove_vehicle(vehicle.id)
            purged += 1
        return CleanupStats(vehicles_purged=purged)
