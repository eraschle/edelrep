from datetime import UTC, date, datetime

import pytest
from ulid import ULID

from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
from edelrep.domain.value_objects import VehicleId


def _vid() -> VehicleId:
    return VehicleId("12345")


def _now() -> datetime:
    return datetime(2026, 5, 2, 10, 0, tzinfo=UTC)


def test_image_source_values() -> None:
    assert ImageSource.MANUAL.value == "manual"
    assert ImageSource.EMAIL.value == "email"
    assert ImageSource("manual") is ImageSource.MANUAL


def test_vehicle_construction_with_optional_fields() -> None:
    v = Vehicle(id=_vid(), vin="WDB123", description="Kran", created_at=_now())
    assert v.id == _vid()
    assert v.vin == "WDB123"


def test_vehicle_allows_none_vin_and_description() -> None:
    v = Vehicle(id=_vid(), vin=None, description=None, created_at=_now())
    assert v.vin is None
    assert v.description is None


def test_vehicle_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Vehicle(id=_vid(), vin=None, description=None, created_at=datetime(2026, 5, 2, 10, 0))


def test_repair_construction() -> None:
    rid = ULID()
    r = Repair(
        id=rid,
        vehicle_id=_vid(),
        date=date(2026, 4, 15),
        description="Brake pads",
        created_at=_now(),
    )
    assert r.id is rid
    assert r.vehicle_id == _vid()
    assert r.date == date(2026, 4, 15)


def test_repair_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Repair(
            id=ULID(),
            vehicle_id=_vid(),
            date=date(2026, 4, 15),
            description="x",
            created_at=datetime(2026, 5, 2, 10, 0),
        )


def test_image_full_construction() -> None:
    rid = ULID()
    iid = ULID()
    captured = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)
    img = Image(
        id=iid,
        repair_id=rid,
        storage_key="12345/2026-04-15__brakes/0001_<ulid>.jpg",
        thumbnail_key="12345/2026-04-15__brakes/_thumbs/0001_<ulid>.jpg",
        filename="0001_<ulid>.jpg",
        mime_type="image/jpeg",
        size_bytes=4096,
        source=ImageSource.MANUAL,
        uploaded_at=_now(),
        captured_at=captured,
    )
    assert img.id is iid
    assert img.repair_id is rid
    assert img.captured_at == captured


def test_image_allows_optional_thumbnail_and_capture() -> None:
    img = Image(
        id=ULID(),
        repair_id=ULID(),
        storage_key="k",
        thumbnail_key=None,
        filename="x.jpg",
        mime_type="image/jpeg",
        size_bytes=1,
        source=ImageSource.EMAIL,
        uploaded_at=_now(),
        captured_at=None,
    )
    assert img.thumbnail_key is None
    assert img.captured_at is None


def test_image_rejects_naive_uploaded_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Image(
            id=ULID(),
            repair_id=ULID(),
            storage_key="k",
            thumbnail_key=None,
            filename="x.jpg",
            mime_type="image/jpeg",
            size_bytes=1,
            source=ImageSource.MANUAL,
            uploaded_at=datetime(2026, 5, 2, 10, 0),
            captured_at=None,
        )


def test_image_rejects_naive_captured_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Image(
            id=ULID(),
            repair_id=ULID(),
            storage_key="k",
            thumbnail_key=None,
            filename="x.jpg",
            mime_type="image/jpeg",
            size_bytes=1,
            source=ImageSource.MANUAL,
            uploaded_at=_now(),
            captured_at=datetime(2026, 4, 15, 12, 0),
        )


def test_image_rejects_negative_size() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        Image(
            id=ULID(),
            repair_id=ULID(),
            storage_key="k",
            thumbnail_key=None,
            filename="x.jpg",
            mime_type="image/jpeg",
            size_bytes=-1,
            source=ImageSource.MANUAL,
            uploaded_at=_now(),
            captured_at=None,
        )


def _aware_now() -> datetime:
    return datetime.now(UTC)


def _build_image(*, comment: str | None = None) -> Image:
    return Image(
        id=ULID(),
        repair_id=ULID(),
        storage_key="",
        thumbnail_key=None,
        filename="x.jpg",
        mime_type="image/jpeg",
        size_bytes=10,
        source=ImageSource.MANUAL,
        uploaded_at=_aware_now(),
        captured_at=None,
        comment=comment,
    )


def test_image_default_comment_is_none() -> None:
    img = _build_image()
    assert img.comment is None


def test_image_accepts_short_comment() -> None:
    img = _build_image(comment="brakes")
    assert img.comment == "brakes"


def test_image_rejects_comment_over_1000_chars() -> None:
    too_long = "x" * 1001
    with pytest.raises(ValueError, match="too long"):
        _build_image(comment=too_long)
