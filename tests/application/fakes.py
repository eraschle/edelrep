from collections.abc import Iterable

from ulid import ULID

from edelrep.domain.entities import Image, Repair, Vehicle
from edelrep.domain.exceptions import (
    DuplicateRegistrationNumber,
    DuplicateRepair,
    DuplicateVin,
    ImageNotFound,
    RepairNotFound,
    VehicleNotFound,
)


class InMemoryVehicleRepo:
    def __init__(self) -> None:
        self._store: dict[ULID, Vehicle] = {}

    def get(self, vehicle_id: ULID) -> Vehicle:
        try:
            return self._store[vehicle_id]
        except KeyError as exc:
            raise VehicleNotFound(str(vehicle_id)) from exc

    def save(self, vehicle: Vehicle) -> None:
        self._guard_unique(vehicle)
        self._store[vehicle.id] = vehicle

    def update(self, vehicle: Vehicle) -> None:
        if vehicle.id not in self._store:
            raise VehicleNotFound(str(vehicle.id))
        self._guard_unique(vehicle)
        self._store[vehicle.id] = vehicle

    def list_all(self) -> Iterable[Vehicle]:
        return list(self._store.values())

    def exists(self, vehicle_id: ULID) -> bool:
        return vehicle_id in self._store

    def find_by_registration(self, registration_number: str) -> Vehicle | None:
        needle = registration_number.strip()
        for v in self._store.values():
            if v.registration_number == needle:
                return v
        return None

    def find_by_vin(self, vin: str) -> Vehicle | None:
        needle = vin.strip().upper()
        for v in self._store.values():
            if v.vin == needle:
                return v
        return None

    def _guard_unique(self, vehicle: Vehicle) -> None:
        if vehicle.registration_number is not None:
            existing = self.find_by_registration(vehicle.registration_number)
            if existing is not None and existing.id != vehicle.id:
                raise DuplicateRegistrationNumber(vehicle.registration_number)
        if vehicle.vin is not None:
            existing = self.find_by_vin(vehicle.vin)
            if existing is not None and existing.id != vehicle.id:
                raise DuplicateVin(vehicle.vin)


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
                    str(repair.vehicle_id),
                    f"{repair.date.isoformat()}__{repair.description}",
                )
        self._store[repair.id] = repair

    def update(self, repair: Repair) -> None:
        if repair.id not in self._store:
            raise RepairNotFound(repair.id)
        self._store[repair.id] = repair

    def list_for_vehicle(self, vehicle_id: ULID) -> Iterable[Repair]:
        return sorted(
            (r for r in self._store.values() if r.vehicle_id == vehicle_id),
            key=lambda r: (r.date, r.created_at),
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
            comment=image.comment,
        )
        self._store[image.id] = (populated, raw_bytes, thumbnail_bytes)

    def list_for_repair(self, repair_id: ULID) -> Iterable[Image]:
        return [entry[0] for entry in self._store.values() if entry[0].repair_id == repair_id]

    def update_comment(self, image_id: ULID, comment: str | None) -> None:
        if image_id not in self._store:
            raise ImageNotFound(image_id)
        img, raw, thumb = self._store[image_id]
        updated = Image(
            id=img.id,
            repair_id=img.repair_id,
            storage_key=img.storage_key,
            thumbnail_key=img.thumbnail_key,
            filename=img.filename,
            mime_type=img.mime_type,
            size_bytes=img.size_bytes,
            source=img.source,
            uploaded_at=img.uploaded_at,
            captured_at=img.captured_at,
            comment=comment,
        )
        self._store[image_id] = (updated, raw, thumb)

    # Convenience helpers for use-case integration tests:
    def raw_bytes_for(self, image_id: ULID) -> bytes:
        return self._store[image_id][1]

    def thumbnail_bytes_for(self, image_id: ULID) -> bytes | None:
        return self._store[image_id][2]


class InMemoryStorageBackend:
    """Minimal fake StorageBackend backed by an InMemoryImageRepo.

    Reads bytes by looking up the storage_key in the image repo's internal
    store so that UploadImageUseCase's duplicate-check can resolve keys.
    """

    def __init__(self, image_repo: InMemoryImageRepo) -> None:
        self._image_repo = image_repo

    def read_bytes(self, key: str) -> bytes:
        for _img, raw, _thumb in self._image_repo._store.values():
            if _img.storage_key == key:
                return raw
        raise FileNotFoundError(key)

    # The remaining StorageBackend methods are not needed for upload tests.
    def write_bytes(self, key: str, data: bytes) -> None:  # pragma: no cover
        raise NotImplementedError

    def open_read(self, key: str):  # pragma: no cover
        raise NotImplementedError

    def delete(self, key: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def exists(self, key: str) -> bool:  # pragma: no cover
        raise NotImplementedError

    def list_prefix(self, prefix: str):  # pragma: no cover
        raise NotImplementedError
