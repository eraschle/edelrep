import re

from edelrep.domain.exceptions import InvalidRegistrationNumber, InvalidVin

_REGISTRATION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_VIN_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,32}$")


def validate_registration_number(value: str) -> str:
    """Normalise and validate a Swiss Stammnummer; raises InvalidRegistrationNumber."""
    cleaned = value.strip()
    if not _REGISTRATION_PATTERN.fullmatch(cleaned):
        raise InvalidRegistrationNumber(value)
    return cleaned


def validate_vin(value: str) -> str:
    """Normalise and validate a Rahmennummer / chassis number; raises InvalidVin."""
    cleaned = value.strip().upper()
    if not _VIN_PATTERN.fullmatch(cleaned):
        raise InvalidVin(value)
    return cleaned
