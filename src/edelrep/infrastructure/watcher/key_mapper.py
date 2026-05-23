import re
from enum import Enum, auto
from pathlib import Path

from edelrep.infrastructure.filesystem.layout import (
    is_image_key,
    is_image_sidecar_key,
    is_repair_sidecar_key,
    is_vehicle_sidecar_key,
)

_TEMP_SUFFIX_RE = re.compile(r"\.tmp\.[0-9a-f]+$")
_THUMB_KEY_RE = re.compile(
    r"^[0-9A-HJKMNP-TV-Z]{26}/\d{4}-\d{2}-\d{2}__[a-z0-9-]+/_thumbs/.+$"
)


class EntityKind(Enum):
    VEHICLE = auto()
    REPAIR = auto()
    IMAGE = auto()
    IMAGE_SIDECAR = auto()
    THUMBNAIL = auto()
    IGNORED = auto()


def path_to_key(path: Path, storage_root: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(storage_root.resolve())
    except ValueError:
        return None
    posix = relative.as_posix()
    return "" if posix == "." else posix


def classify(key: str) -> EntityKind:
    if _THUMB_KEY_RE.match(key):
        return EntityKind.THUMBNAIL
    if is_vehicle_sidecar_key(key):
        return EntityKind.VEHICLE
    if is_repair_sidecar_key(key):
        return EntityKind.REPAIR
    if is_image_sidecar_key(key):
        return EntityKind.IMAGE_SIDECAR
    if is_image_key(key):
        return EntityKind.IMAGE
    return EntityKind.IGNORED


def is_temp_atomic_write(path: Path) -> bool:
    return bool(_TEMP_SUFFIX_RE.search(path.name))
