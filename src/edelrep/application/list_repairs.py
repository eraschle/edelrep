from ulid import ULID

from edelrep.domain.entities import Repair
from edelrep.domain.exceptions import VehicleNotFound
from edelrep.domain.ports import RepairRepository, VehicleRepository


class ListRepairsUseCase:
    """List a vehicle's repairs, newest first."""

    def __init__(
        self,
        vehicle_repo: VehicleRepository,
        repair_repo: RepairRepository,
    ) -> None:
        self._vehicle_repo = vehicle_repo
        self._repair_repo = repair_repo

    def execute(self, vehicle_id: ULID) -> list[Repair]:
        if not self._vehicle_repo.exists(vehicle_id):
            raise VehicleNotFound(str(vehicle_id))
        return list(self._repair_repo.list_for_vehicle(vehicle_id))
