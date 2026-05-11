from collections.abc import Iterable

from ulid import ULID

from edelrep.domain.entities import Repair
from edelrep.domain.exceptions import DuplicateRepair, RepairNotFound, VehicleNotFound
from edelrep.domain.ports import StorageBackend
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.json_codec import (
    parse_aware_datetime,
    parse_date,
    parse_ulid,
)
from edelrep.infrastructure.filesystem.layout import (
    is_repair_sidecar_key,
    repair_dir_name,
    repair_sidecar_key,
    vehicle_sidecar_key,
)
from edelrep.infrastructure.filesystem.sidecar import (
    read_backend_sidecar,
    write_backend_sidecar,
)


class FilesystemRepairRepository:
    """RepairRepository implementation against any StorageBackend.

    Layout: ``<reg_no>/<YYYY-MM-DD>__<slug>/_repair.json``.
    """

    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend

    def get(self, repair_id: ULID) -> Repair:
        for key in self._backend.list_prefix(""):
            if not is_repair_sidecar_key(key):
                continue
            data = read_backend_sidecar(self._backend, key)
            if parse_ulid(str(data["id"])) == repair_id:
                vid = VehicleId(key.split("/", 1)[0])
                return _deserialise(vid, data)
        raise RepairNotFound(repair_id)

    def save(self, repair: Repair) -> None:
        if not self._backend.exists(vehicle_sidecar_key(repair.vehicle_id)):
            raise VehicleNotFound(repair.vehicle_id.registration_number)
        dir_name = repair_dir_name(repair.date, repair.description)
        key = repair_sidecar_key(repair.vehicle_id, dir_name)
        if self._backend.exists(key):
            raise DuplicateRepair(repair.vehicle_id.registration_number, dir_name)
        write_backend_sidecar(self._backend, key, _serialise(repair))

    def update(self, repair: Repair) -> None:
        for key in self._backend.list_prefix(""):
            if not is_repair_sidecar_key(key):
                continue
            data = read_backend_sidecar(self._backend, key)
            sidecar_reg_no = key.split("/", 1)[0]
            if (
                parse_ulid(str(data["id"])) == repair.id
                and sidecar_reg_no == repair.vehicle_id.registration_number
            ):
                write_backend_sidecar(self._backend, key, _serialise(repair))
                return
        raise RepairNotFound(repair.id)

    def list_for_vehicle(self, vehicle_id: VehicleId) -> Iterable[Repair]:
        if not self._backend.exists(vehicle_sidecar_key(vehicle_id)):
            return
        prefix = f"{vehicle_id.registration_number}/"
        repairs: list[Repair] = []
        for key in self._backend.list_prefix(prefix):
            if not is_repair_sidecar_key(key):
                continue
            data = read_backend_sidecar(self._backend, key)
            repairs.append(_deserialise(vehicle_id, data))
        repairs.sort(key=lambda r: (r.date, r.created_at), reverse=True)
        yield from repairs


def _serialise(repair: Repair) -> dict[str, object]:
    return {
        "id": str(repair.id),
        "date": repair.date,
        "description": repair.description,
        "created_at": repair.created_at,
    }


def _deserialise(vehicle_id: VehicleId, data: dict[str, object]) -> Repair:
    return Repair(
        id=parse_ulid(str(data["id"])),
        vehicle_id=vehicle_id,
        date=parse_date(str(data["date"])),
        description=str(data["description"]),
        created_at=parse_aware_datetime(str(data["created_at"])),
    )
