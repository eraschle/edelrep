from datetime import UTC, datetime

from ulid import ULID

from edelrep.domain.entities import Vehicle
from edelrep.domain.ports import SearchIndex, VehicleRepository


class CreateVehicleUseCase:
    """Create and persist a new vehicle, then index it for search."""

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
        registration_number: str | None,
        vin: str | None,
        description: str | None,
    ) -> Vehicle:
        vehicle = Vehicle(
            id=ULID(),
            registration_number=registration_number or None,
            vin=vin or None,
            description=description or None,
            created_at=datetime.now(UTC),
        )
        self._vehicle_repo.save(vehicle)
        self._search_index.upsert_vehicle(vehicle)
        return vehicle
