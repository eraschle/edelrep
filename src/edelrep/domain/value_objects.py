import re
from dataclasses import dataclass

from edelrep.domain.exceptions import InvalidVehicleId

_REGISTRATION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@dataclass(frozen=True, slots=True)
class VehicleId:
    """Permanent Swiss vehicle registration number (Stammnummer)."""

    registration_number: str

    def __post_init__(self) -> None:
        if not _REGISTRATION_PATTERN.fullmatch(self.registration_number):
            raise InvalidVehicleId(self.registration_number)
