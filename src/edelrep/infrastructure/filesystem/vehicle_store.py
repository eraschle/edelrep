from collections.abc import Iterable

from ulid import ULID

from edelrep.domain.entities import Vehicle
from edelrep.domain.exceptions import (
    DuplicateRegistrationNumber,
    DuplicateVin,
    VehicleNotFound,
)
from edelrep.domain.ports import StorageBackend
from edelrep.infrastructure.filesystem.json_codec import parse_aware_datetime, parse_ulid
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

    Layout: ``<vehicle_ulid>/_vehicle.json`` sidecars under the storage root.
    The sidecar carries the optional Stammnummer (``registration_number``)
    and optional Rahmennummer (``vin``); at least one of them must be set
    by domain invariant.
    """

    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend

    def get(self, vehicle_id: ULID) -> Vehicle:
        key = vehicle_sidecar_key(vehicle_id)
        if not self._backend.exists(key):
            raise VehicleNotFound(str(vehicle_id))
        data = read_backend_sidecar(self._backend, key)
        return _deserialise(vehicle_id, data)

    def save(self, vehicle: Vehicle) -> None:
        self._guard_unique_identifiers(vehicle)
        key = vehicle_sidecar_key(vehicle.id)
        write_backend_sidecar(self._backend, key, _serialise(vehicle))

    def update(self, vehicle: Vehicle) -> None:
        key = vehicle_sidecar_key(vehicle.id)
        if not self._backend.exists(key):
            raise VehicleNotFound(str(vehicle.id))
        self._guard_unique_identifiers(vehicle)
        write_backend_sidecar(self._backend, key, _serialise(vehicle))

    def exists(self, vehicle_id: ULID) -> bool:
        return self._backend.exists(vehicle_sidecar_key(vehicle_id))

    def list_all(self) -> Iterable[Vehicle]:
        for key in sorted(self._backend.list_prefix("")):
            if not is_vehicle_sidecar_key(key):
                continue
            try:
                vid = parse_ulid(key.split("/", 1)[0])
            except ValueError:
                continue
            data = read_backend_sidecar(self._backend, key)
            yield _deserialise(vid, data)

    def find_by_registration(self, registration_number: str) -> Vehicle | None:
        needle = registration_number.strip()
        for vehicle in self.list_all():
            if vehicle.registration_number == needle:
                return vehicle
        return None

    def find_by_vin(self, vin: str) -> Vehicle | None:
        needle = vin.strip().upper()
        for vehicle in self.list_all():
            if vehicle.vin == needle:
                return vehicle
        return None

    def _guard_unique_identifiers(self, vehicle: Vehicle) -> None:
        if vehicle.registration_number is not None:
            existing = self.find_by_registration(vehicle.registration_number)
            if existing is not None and existing.id != vehicle.id:
                raise DuplicateRegistrationNumber(vehicle.registration_number)
        if vehicle.vin is not None:
            existing = self.find_by_vin(vehicle.vin)
            if existing is not None and existing.id != vehicle.id:
                raise DuplicateVin(vehicle.vin)


def _serialise(vehicle: Vehicle) -> dict[str, object]:
    return {
        "id": str(vehicle.id),
        "registration_number": vehicle.registration_number,
        "vin": vehicle.vin,
        "description": vehicle.description,
        "created_at": vehicle.created_at,
    }


def _deserialise(vehicle_id: ULID, data: dict[str, object]) -> Vehicle:
    created_at_raw = data["created_at"]
    if not isinstance(created_at_raw, str):  # pragma: no cover - defensive; sidecar produces strings
        raise TypeError(f"created_at must be ISO string, got {type(created_at_raw).__name__}")
    registration_number = data.get("registration_number")
    vin = data.get("vin")
    description = data.get("description")
    return Vehicle(
        id=vehicle_id,
        registration_number=str(registration_number) if registration_number is not None else None,
        vin=str(vin) if vin is not None else None,
        description=str(description) if description is not None else None,
        created_at=parse_aware_datetime(created_at_raw),
    )
