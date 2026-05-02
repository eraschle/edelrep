from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from ulid import ULID

from edelrep.domain.value_objects import VehicleId


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field} must be timezone-aware")


class ImageSource(StrEnum):
    MANUAL = "manual"
    EMAIL = "email"


@dataclass(frozen=True, slots=True)
class Vehicle:
    id: VehicleId
    vin: str | None
    description: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class Repair:
    id: ULID
    vehicle_id: VehicleId
    date: date
    description: str
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

    def __post_init__(self) -> None:
        _require_aware(self.uploaded_at, "uploaded_at")
        if self.captured_at is not None:
            _require_aware(self.captured_at, "captured_at")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
