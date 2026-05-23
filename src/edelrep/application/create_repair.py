from datetime import UTC, date as _date, datetime

from ulid import ULID

from edelrep.domain.entities import Repair
from edelrep.domain.exceptions import VehicleNotFound
from edelrep.domain.ports import RepairRepository, VehicleRepository


class CreateRepairUseCase:
    """Create and persist a new repair under an existing vehicle."""

    def __init__(
        self,
        vehicle_repo: VehicleRepository,
        repair_repo: RepairRepository,
    ) -> None:
        self._vehicle_repo = vehicle_repo
        self._repair_repo = repair_repo

    def execute(
        self,
        *,
        vehicle_id: ULID,
        repair_date: _date,
        description: str | None,
    ) -> Repair:
        if not self._vehicle_repo.exists(vehicle_id):
            raise VehicleNotFound(str(vehicle_id))
        repair = Repair(
            id=ULID(),
            vehicle_id=vehicle_id,
            date=repair_date,
            description=description,
            created_at=datetime.now(UTC),
        )
        self._repair_repo.save(repair)
        return repair
