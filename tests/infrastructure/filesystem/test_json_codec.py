import json
from datetime import UTC, date, datetime
from enum import Enum

import pytest
from ulid import ULID

from edelrep.domain.entities import ImageSource
from edelrep.infrastructure.filesystem.json_codec import (
    DomainJSONEncoder,
    parse_aware_datetime,
    parse_date,
    parse_ulid,
)


def test_encoder_serialises_aware_datetime() -> None:
    dt = datetime(2026, 5, 2, 10, 0, tzinfo=UTC)
    out = json.dumps({"t": dt}, cls=DomainJSONEncoder)
    assert "2026-05-02T10:00:00+00:00" in out


def test_encoder_rejects_naive_datetime() -> None:
    dt = datetime(2026, 5, 2, 10, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        json.dumps({"t": dt}, cls=DomainJSONEncoder)


def test_encoder_serialises_date() -> None:
    out = json.dumps({"d": date(2026, 4, 15)}, cls=DomainJSONEncoder)
    assert '"2026-04-15"' in out


def test_encoder_serialises_ulid() -> None:
    uid = ULID()
    out = json.dumps({"id": uid}, cls=DomainJSONEncoder)
    assert str(uid) in out


def test_encoder_serialises_vehicle_id() -> None:
    # Vehicles are now identified by ULID; the encoder must serialise ULIDs as
    # their canonical 26-char Crockford base32 string.
    uid = ULID.from_str("01J9TGZP6X2K0V3W7Y8Z4QFFFF")
    out = json.dumps({"v": uid}, cls=DomainJSONEncoder)
    assert '"01J9TGZP6X2K0V3W7Y8Z4QFFFF"' in out


def test_encoder_serialises_image_source() -> None:
    out = json.dumps({"s": ImageSource.MANUAL}, cls=DomainJSONEncoder)
    assert '"manual"' in out


def test_parse_aware_datetime_round_trip() -> None:
    dt = datetime(2026, 5, 2, 10, 0, tzinfo=UTC)
    assert parse_aware_datetime(dt.isoformat()) == dt


def test_parse_aware_datetime_rejects_naive() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_aware_datetime("2026-05-02T10:00:00")


def test_parse_date_round_trip() -> None:
    assert parse_date("2026-04-15") == date(2026, 4, 15)


def test_parse_ulid_round_trip() -> None:
    uid = ULID()
    assert parse_ulid(str(uid)) == uid


def test_encoder_serialises_non_str_enum() -> None:
    class Colour(Enum):
        RED = 1

    out = json.dumps({"c": Colour.RED}, cls=DomainJSONEncoder)
    assert '"c": 1' in out
