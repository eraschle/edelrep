from collections.abc import Iterable

from edelrep.domain.entities import Vehicle
from edelrep.domain.exceptions import (
    DuplicateVehicle,
    InvalidVehicleId,
    VehicleNotFound,
)
from edelrep.domain.ports import StorageBackend
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.json_codec import parse_aware_datetime
from edelrep.infrastructure.filesystem.layout import (
    is_vehicle_sidecar_key,
    vehicle_sidecar_key,
)
from edelrep.infrastructure.filesystem.sidecar import (
    read_backend_sidecar,
    write_backend_sidecar,
)


class FilesystemVehicleRepository:
    """VehicleRepository implementation against any StorageBackend.

    Layout convention is unchanged from Phase 2: ``<reg_no>/_vehicle.json``
    sidecars under the storage root. The backend handles all I/O.
    """

    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend

    def get(self, vehicle_id: VehicleId) -> Vehicle:
        key = vehicle_sidecar_key(vehicle_id)
        if not self._backend.exists(key):
            raise VehicleNotFound(vehicle_id.registration_number)
        data = read_backend_sidecar(self._backend, key)
        return _deserialise(vehicle_id, data)

    def save(self, vehicle: Vehicle) -> None:
        key = vehicle_sidecar_key(vehicle.id)
        if self._backend.exists(key):
            raise DuplicateVehicle(vehicle.id.registration_number)
        write_backend_sidecar(self._backend, key, _serialise(vehicle))

    def update(self, vehicle: Vehicle) -> None:
        key = vehicle_sidecar_key(vehicle.id)
        if not self._backend.exists(key):
            raise VehicleNotFound(vehicle.id.registration_number)
        write_backend_sidecar(self._backend, key, _serialise(vehicle))

    def exists(self, vehicle_id: VehicleId) -> bool:
        return self._backend.exists(vehicle_sidecar_key(vehicle_id))

    def list_all(self) -> Iterable[Vehicle]:
        for key in sorted(self._backend.list_prefix("")):
            if not is_vehicle_sidecar_key(key):
                continue
            reg_no = key.split("/", 1)[0]
            try:
                vid = VehicleId(reg_no)
            except InvalidVehicleId:
                continue
            data = read_backend_sidecar(self._backend, key)
            yield _deserialise(vid, data)


def _serialise(vehicle: Vehicle) -> dict[str, object]:
    return {
        "registration_number": vehicle.id.registration_number,
        "vin": vehicle.vin,
        "description": vehicle.description,
        "created_at": vehicle.created_at,
    }


def _deserialise(vehicle_id: VehicleId, data: dict[str, object]) -> Vehicle:
    created_at_raw = data["created_at"]
    if not isinstance(created_at_raw, str):  # pragma: no cover - defensive; sidecar produces strings
        raise TypeError(f"created_at must be ISO string, got {type(created_at_raw).__name__}")
    return Vehicle(
        id=vehicle_id,
        vin=data.get("vin"),  # type: ignore[arg-type]
        description=data.get("description"),  # type: ignore[arg-type]
        created_at=parse_aware_datetime(created_at_raw),
    )
