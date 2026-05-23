"""Helpers for translating user-facing vehicle keys to repository lookups.

URLs accept either the internal ULID, the Stammnummer, or the Rahmennummer
so links remain readable while the persisted identity stays an opaque ULID.
"""

from __future__ import annotations

import re

from ulid import ULID

from edelrep.domain.entities import Vehicle
from edelrep.domain.exceptions import VehicleNotFound
from edelrep.domain.ports import VehicleRepository

_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def resolve_vehicle(repo: VehicleRepository, key: str) -> Vehicle:
    """Return the vehicle for ``key`` or raise :class:`VehicleNotFound`."""
    if _ULID_RE.fullmatch(key):
        try:
            return repo.get(ULID.from_str(key))
        except (ValueError, VehicleNotFound):
            pass
    by_reg = repo.find_by_registration(key)
    if by_reg is not None:
        return by_reg
    by_vin = repo.find_by_vin(key)
    if by_vin is not None:
        return by_vin
    raise VehicleNotFound(key)


def vehicle_url_key(vehicle: Vehicle) -> str:
    """Pick the friendliest URL key for a vehicle (Stammnummer > Rahmen > ULID)."""
    if vehicle.registration_number:
        return vehicle.registration_number
    if vehicle.vin:
        return vehicle.vin
    return str(vehicle.id)


def vehicle_url(vehicle: Vehicle) -> str:
    return f"/vehicles/{vehicle_url_key(vehicle)}"
