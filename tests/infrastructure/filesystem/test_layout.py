from datetime import date
from pathlib import Path

import pytest
from ulid import ULID

from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.layout import (
    image_filename,
    image_key,
    image_sidecar_key,
    is_image_key,
    is_image_sidecar_key,
    is_repair_sidecar_key,
    is_vehicle_sidecar_key,
    repair_dir_name,
    repair_sidecar_key,
    repair_sidecar_path,
    slugify,
    thumbnail_key,
    thumbnail_path,
    unique_repair_dir_name,
    vehicle_dir,
    vehicle_sidecar_key,
    vehicle_sidecar_path,
)


def test_vehicle_dir_uses_registration_number() -> None:
    root = Path("/storage")
    assert vehicle_dir(root, VehicleId("12345")) == root / "12345"


def test_vehicle_sidecar_path() -> None:
    root = Path("/storage")
    assert vehicle_sidecar_path(root, VehicleId("12345")) == root / "12345" / "_vehicle.json"


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Bremsbeläge vorne erneuert", "bremsbelage-vorne-erneuert"),
        ("  whitespace  trimmed  ", "whitespace-trimmed"),
        ("Übergrosse Ümlaute & Sonderzeichen!", "ubergrosse-umlaute-sonderzeichen"),
        ("UPPERCASE", "uppercase"),
        ("a/b/c", "a-b-c"),
        ("", "repair"),
        ("---", "repair"),
        ("   ", "repair"),
        ("a" * 60, "a" * 40),
    ],
)
def test_slugify(description: str, expected: str) -> None:
    assert slugify(description) == expected


def test_repair_dir_name_format() -> None:
    name = repair_dir_name(date(2026, 4, 15), "Bremsen vorne")
    assert name == "2026-04-15__bremsen-vorne"


def test_repair_sidecar_path() -> None:
    root = Path("/storage")
    p = repair_sidecar_path(root, VehicleId("12345"), "2026-04-15__bremsen-vorne")
    assert p == root / "12345" / "2026-04-15__bremsen-vorne" / "_repair.json"


def test_image_filename_format() -> None:
    uid = ULID.from_str("01J9TGZP6X2K0V3W7Y8Z4QABCD")
    assert image_filename(seq=1, image_id=uid, extension="jpg") == "0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg"
    assert image_filename(seq=42, image_id=uid, extension="png") == "0042_01J9TGZP6X2K0V3W7Y8Z4QABCD.png"


def test_image_filename_zero_pads_to_four_digits() -> None:
    uid = ULID()
    assert image_filename(seq=9999, image_id=uid, extension="jpg").startswith("9999_")


def test_image_filename_rejects_seq_out_of_range() -> None:
    uid = ULID()
    with pytest.raises(ValueError, match="seq"):
        image_filename(seq=0, image_id=uid, extension="jpg")
    with pytest.raises(ValueError, match="seq"):
        image_filename(seq=10000, image_id=uid, extension="jpg")


def test_thumbnail_path() -> None:
    repair_dir = Path("/storage/12345/2026-04-15__brakes")
    thumb = thumbnail_path(repair_dir, "0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg")
    assert thumb == repair_dir / "_thumbs" / "0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg"


def test_unique_repair_dir_name_no_collision(tmp_path: Path) -> None:
    base = "2026-04-15__brakes"
    assert unique_repair_dir_name(tmp_path, base) == base


def test_unique_repair_dir_name_one_collision(tmp_path: Path) -> None:
    base = "2026-04-15__brakes"
    (tmp_path / base).mkdir()
    assert unique_repair_dir_name(tmp_path, base) == f"{base}-2"


def test_unique_repair_dir_name_multiple_collisions(tmp_path: Path) -> None:
    base = "2026-04-15__brakes"
    (tmp_path / base).mkdir()
    (tmp_path / f"{base}-2").mkdir()
    (tmp_path / f"{base}-3").mkdir()
    assert unique_repair_dir_name(tmp_path, base) == f"{base}-4"


def test_vehicle_sidecar_key() -> None:
    assert vehicle_sidecar_key(VehicleId("12345")) == "12345/_vehicle.json"


def test_repair_sidecar_key() -> None:
    key = repair_sidecar_key(VehicleId("12345"), "2026-04-15__brakes")
    assert key == "12345/2026-04-15__brakes/_repair.json"


def test_image_key_format() -> None:
    assert (
        image_key(
            VehicleId("12345"),
            "2026-04-15__brakes",
            "0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg",
        )
        == "12345/2026-04-15__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg"
    )


def test_thumbnail_key_format() -> None:
    assert (
        thumbnail_key(
            VehicleId("12345"),
            "2026-04-15__brakes",
            "0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg",
        )
        == "12345/2026-04-15__brakes/_thumbs/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg"
    )


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("12345/_vehicle.json", True),
        ("12345/2026-04-15__brakes/_repair.json", False),
        ("_system/inbox/foo.eml", False),
        ("12345/_vehicle.json/extra", False),
        ("12345/", False),
        ("", False),
    ],
)
def test_is_vehicle_sidecar_key(key: str, expected: bool) -> None:
    assert is_vehicle_sidecar_key(key) is expected


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("12345/2026-04-15__brakes/_repair.json", True),
        ("12345/_vehicle.json", False),
        ("12345/2026-04-15__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg", False),
        ("12345/2026-04-15__BRAKES/_repair.json", False),
        ("_system/inbox/_repair.json", False),
    ],
)
def test_is_repair_sidecar_key(key: str, expected: bool) -> None:
    assert is_repair_sidecar_key(key) is expected


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("12345/2026-04-15__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg", True),
        ("12345/2026-04-15__brakes/_thumbs/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg", False),
        ("12345/2026-04-15__brakes/_repair.json", False),
        ("12345/_vehicle.json", False),
        ("12345/2026-04-15__brakes/badname.jpg", False),
    ],
)
def test_is_image_key(key: str, expected: bool) -> None:
    assert is_image_key(key) is expected


def test_image_sidecar_key_replaces_extension_with_json() -> None:
    vid = VehicleId("12345")
    key = image_sidecar_key(vid, "2026-05-10__brakes", "0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg")
    assert key == "12345/2026-05-10__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.json"


def test_is_image_sidecar_key_accepts_valid() -> None:
    assert is_image_sidecar_key("12345/2026-05-10__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.json")


def test_is_image_sidecar_key_rejects_repair_sidecar() -> None:
    assert not is_image_sidecar_key("12345/2026-05-10__brakes/_repair.json")


def test_is_image_sidecar_key_rejects_image_jpg() -> None:
    assert not is_image_sidecar_key("12345/2026-05-10__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg")
