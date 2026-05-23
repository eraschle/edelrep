from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from ulid import ULID

from edelrep.domain._datetime_guards import require_aware as _require_aware
from edelrep.domain.exceptions import VehicleIdentifierRequired
from edelrep.domain.value_objects import (
    validate_registration_number,
    validate_vin,
)


class ImageSource(StrEnum):
    MANUAL = "manual"
    EMAIL = "email"


@dataclass(frozen=True, slots=True)
class Vehicle:
    id: ULID
    registration_number: str | None
    vin: str | None
    description: str | None
    created_at: datetime
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")
        if self.deleted_at is not None:
            _require_aware(self.deleted_at, "deleted_at")
        if self.registration_number is not None:
            object.__setattr__(
                self,
                "registration_number",
                validate_registration_number(self.registration_number),
            )
        if self.vin is not None:
            object.__setattr__(self, "vin", validate_vin(self.vin))
        if self.registration_number is None and self.vin is None:
            raise VehicleIdentifierRequired

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


@dataclass(frozen=True, slots=True)
class Repair:
    id: ULID
    vehicle_id: ULID
    date: date
    description: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class Image:
    id: ULID
    repair_id: ULID
    storage_key: str
    thumbnail_key: str | None
    filename: str
    mime_type: str
    size_bytes: int
    source: ImageSource
    uploaded_at: datetime
    captured_at: datetime | None
    comment: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.uploaded_at, "uploaded_at")
        if self.captured_at is not None:
            _require_aware(self.captured_at, "captured_at")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        if self.comment is not None and len(self.comment) > 1000:
            raise ValueError("comment too long (max 1000 chars)")
