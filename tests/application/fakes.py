from collections.abc import Iterable

from ulid import ULID

from edelrep.domain.entities import Image, Repair, Vehicle
from edelrep.domain.exceptions import (
    DuplicateRepair,
    DuplicateVehicle,
    ImageNotFound,
    RepairNotFound,
    VehicleNotFound,
)
from edelrep.domain.value_objects import VehicleId


class InMemoryVehicleRepo:
    def __init__(self) -> None:
        self._store: dict[VehicleId, Vehicle] = {}

    def get(self, vehicle_id: VehicleId) -> Vehicle:
        try:
            return self._store[vehicle_id]
        except KeyError as exc:
            raise VehicleNotFound(vehicle_id.registration_number) from exc

    def save(self, vehicle: Vehicle) -> None:
        if vehicle.id in self._store:
            raise DuplicateVehicle(vehicle.id.registration_number)
        self._store[vehicle.id] = vehicle

    def update(self, vehicle: Vehicle) -> None:
        if vehicle.id not in self._store:
            raise VehicleNotFound(vehicle.id.registration_number)
        self._store[vehicle.id] = vehicle

    def list_all(self) -> Iterable[Vehicle]:
        return list(self._store.values())

    def exists(self, vehicle_id: VehicleId) -> bool:
        return vehicle_id in self._store


class InMemoryRepairRepo:
    def __init__(self) -> None:
        self._store: dict[ULID, Repair] = {}

    def get(self, repair_id: ULID) -> Repair:
        try:
            return self._store[repair_id]
        except KeyError as exc:
            raise RepairNotFound(repair_id) from exc

    def save(self, repair: Repair) -> None:
        for existing in self._store.values():
            if (
                existing.vehicle_id == repair.vehicle_id
                and existing.date == repair.date
                and existing.description == repair.description
            ):
                raise DuplicateRepair(
                    repair.vehicle_id.registration_number,
                    f"{repair.date.isoformat()}__{repair.description}",
                )
        self._store[repair.id] = repair

    def update(self, repair: Repair) -> None:
        if repair.id not in self._store:
            raise RepairNotFound(repair.id)
        self._store[repair.id] = repair

    def list_for_vehicle(self, vehicle_id: VehicleId) -> Iterable[Repair]:
        return sorted(
            (r for r in self._store.values() if r.vehicle_id == vehicle_id),
            key=lambda r: r.date,
            reverse=True,
        )


class InMemoryImageRepo:
    def __init__(self) -> None:
        self._store: dict[ULID, tuple[Image, bytes, bytes | None]] = {}

    def get(self, image_id: ULID) -> Image:
        try:
            return self._store[image_id][0]
        except KeyError as exc:
            raise ImageNotFound(image_id) from exc

    def save(
        self,
        image: Image,
        *,
        raw_bytes: bytes,
        thumbnail_bytes: bytes | None = None,
    ) -> None:
        synthetic_key = f"<memory>/{image.repair_id}/{image.id}.{image.filename.rsplit('.', 1)[-1]}"
        synthetic_thumb = f"{synthetic_key}.thumb" if thumbnail_bytes is not None else None
        populated = Image(
            id=image.id,
            repair_id=image.repair_id,
            storage_key=synthetic_key,
            thumbnail_key=synthetic_thumb,
            filename=image.filename,
            mime_type=image.mime_type,
            size_bytes=len(raw_bytes),
            source=image.source,
            uploaded_at=image.uploaded_at,
            captured_at=image.captured_at,
        )
        self._store[image.id] = (populated, raw_bytes, thumbnail_bytes)

    def list_for_repair(self, repair_id: ULID) -> Iterable[Image]:
        return [entry[0] for entry in self._store.values() if entry[0].repair_id == repair_id]

    # Convenience helpers for use-case integration tests:
    def raw_bytes_for(self, image_id: ULID) -> bytes:
        return self._store[image_id][1]

    def thumbnail_bytes_for(self, image_id: ULID) -> bytes | None:
        return self._store[image_id][2]
