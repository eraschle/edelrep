from collections.abc import Iterable
from pathlib import Path

from edelrep.domain.entities import Vehicle
from edelrep.domain.exceptions import DuplicateVehicle, VehicleNotFound
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.json_codec import parse_aware_datetime
from edelrep.infrastructure.filesystem.layout import vehicle_dir, vehicle_sidecar_path
from edelrep.infrastructure.filesystem.sidecar import read_sidecar, write_sidecar


class FilesystemVehicleRepository:
    """VehicleRepository implementation backed by JSON sidecars on disk."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def get(self, vehicle_id: VehicleId) -> Vehicle:
        sidecar = vehicle_sidecar_path(self._root, vehicle_id)
        if not sidecar.is_file():
            raise VehicleNotFound(vehicle_id.registration_number)
        data = read_sidecar(sidecar)
        return self._deserialise(vehicle_id, data)

    def save(self, vehicle: Vehicle) -> None:
        directory = vehicle_dir(self._root, vehicle.id)
        if directory.exists():
            raise DuplicateVehicle(vehicle.id.registration_number)
        directory.mkdir(parents=True)
        write_sidecar(vehicle_sidecar_path(self._root, vehicle.id), self._serialise(vehicle))

    def update(self, vehicle: Vehicle) -> None:
        directory = vehicle_dir(self._root, vehicle.id)
        if not directory.is_dir():
            raise VehicleNotFound(vehicle.id.registration_number)
        write_sidecar(vehicle_sidecar_path(self._root, vehicle.id), self._serialise(vehicle))

    def exists(self, vehicle_id: VehicleId) -> bool:
        return vehicle_sidecar_path(self._root, vehicle_id).is_file()

    def list_all(self) -> Iterable[Vehicle]:
        if not self._root.is_dir():
            return
        for entry in sorted(self._root.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_"):
                continue
            sidecar = entry / "_vehicle.json"
            if not sidecar.is_file():
                continue
            try:
                vid = VehicleId(entry.name)
            except Exception:  # filename may not be a valid VehicleId
                continue
            data = read_sidecar(sidecar)
            yield self._deserialise(vid, data)

    @staticmethod
    def _serialise(vehicle: Vehicle) -> dict[str, object]:
        return {
            "registration_number": vehicle.id.registration_number,
            "vin": vehicle.vin,
            "description": vehicle.description,
            "created_at": vehicle.created_at,
        }

    @staticmethod
    def _deserialise(vehicle_id: VehicleId, data: dict[str, object]) -> Vehicle:
        created_at_raw = data["created_at"]
        if not isinstance(created_at_raw, str):
            raise TypeError(f"created_at must be ISO string, got {type(created_at_raw).__name__}")
        return Vehicle(
            id=vehicle_id,
            vin=data.get("vin"),  # type: ignore[arg-type]
            description=data.get("description"),  # type: ignore[arg-type]
            created_at=parse_aware_datetime(created_at_raw),
        )
