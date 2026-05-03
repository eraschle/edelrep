from edelrep.domain.entities import Repair
from edelrep.domain.exceptions import VehicleNotFound
from edelrep.domain.ports import RepairRepository, VehicleRepository
from edelrep.domain.value_objects import VehicleId


class ListRepairsUseCase:
    """List a vehicle's repairs, newest first."""

    def __init__(
        self,
        vehicle_repo: VehicleRepository,
        repair_repo: RepairRepository,
    ) -> None:
        self._vehicle_repo = vehicle_repo
        self._repair_repo = repair_repo

    def execute(self, vehicle_id: VehicleId) -> list[Repair]:
        if not self._vehicle_repo.exists(vehicle_id):
            raise VehicleNotFound(vehicle_id.registration_number)
        return list(self._repair_repo.list_for_vehicle(vehicle_id))
