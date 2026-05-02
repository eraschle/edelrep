import json
from datetime import date, datetime
from enum import Enum
from typing import Any

from ulid import ULID

from edelrep.domain.value_objects import VehicleId


class DomainJSONEncoder(json.JSONEncoder):
    """JSON encoder that knows how to serialise edelrep's domain primitives."""

    def default(self, o: Any) -> Any:
        if isinstance(o, datetime):
            if o.tzinfo is None or o.tzinfo.utcoffset(o) is None:
                raise ValueError("datetime values must be timezone-aware before encoding")
            return o.isoformat()
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, ULID):
            return str(o)
        if isinstance(o, VehicleId):
            return o.registration_number
        if isinstance(o, Enum):
            return o.value
        return super().default(o)


def parse_aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise ValueError(f"datetime {value!r} must be timezone-aware")
    return parsed


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_ulid(value: str) -> ULID:
    return ULID.from_str(value)
