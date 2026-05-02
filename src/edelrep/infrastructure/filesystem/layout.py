import re
import unicodedata
from datetime import date
from pathlib import Path

from ulid import ULID

from edelrep.domain.value_objects import VehicleId

_SLUG_MAX_LEN = 40
_SLUG_FALLBACK = "repair"
_SLUG_NORMALISE_RE = re.compile(r"[^a-z0-9]+")
_SLUG_TRIM_RE = re.compile(r"^-+|-+$")


def vehicle_dir(root: Path, vehicle_id: VehicleId) -> Path:
    return root / vehicle_id.registration_number


def vehicle_sidecar_path(root: Path, vehicle_id: VehicleId) -> Path:
    return vehicle_dir(root, vehicle_id) / "_vehicle.json"


def slugify(description: str) -> str:
    normalised = unicodedata.normalize("NFKD", description)
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii").lower()
    hyphenated = _SLUG_NORMALISE_RE.sub("-", ascii_only)
    trimmed = _SLUG_TRIM_RE.sub("", hyphenated)
    truncated = trimmed[:_SLUG_MAX_LEN]
    truncated = _SLUG_TRIM_RE.sub("", truncated)
    return truncated or _SLUG_FALLBACK


def repair_dir_name(repair_date: date, description: str) -> str:
    return f"{repair_date.isoformat()}__{slugify(description)}"


def repair_sidecar_path(root: Path, vehicle_id: VehicleId, dir_name: str) -> Path:
    return vehicle_dir(root, vehicle_id) / dir_name / "_repair.json"


def image_filename(*, seq: int, image_id: ULID, extension: str) -> str:
    if not 1 <= seq <= 9999:
        raise ValueError(f"seq must be in 1..9999, got {seq}")
    return f"{seq:04d}_{image_id!s}.{extension}"


def thumbnail_path(repair_dir: Path, image_filename_value: str) -> Path:
    return repair_dir / "_thumbs" / image_filename_value


def unique_repair_dir_name(parent: Path, base: str) -> str:
    """Return a collision-free name under ``parent``.

    Not safe under concurrent writers — V1 is single-process per PLAN.md §2.
    """
    if not (parent / base).exists():
        return base
    n = 2
    while (parent / f"{base}-{n}").exists():
        n += 1
    return f"{base}-{n}"
