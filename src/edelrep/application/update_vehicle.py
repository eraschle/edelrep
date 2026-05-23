from ulid import ULID

from edelrep.domain.entities import Vehicle
from edelrep.domain.ports import SearchIndex, VehicleRepository


class UpdateVehicleUseCase:
    """Update an existing vehicle and re-project it into the search index."""

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
        vehicle_id: ULID,
        registration_number: str | None,
        vin: str | None,
        description: str | None,
    ) -> Vehicle:
        existing = self._vehicle_repo.get(vehicle_id)
        updated = Vehicle(
            id=existing.id,
            registration_number=registration_number or None,
            vin=vin or None,
            description=description or None,
            created_at=existing.created_at,
        )
        self._vehicle_repo.update(updated)
        self._search_index.upsert_vehicle(updated)
        return updated
