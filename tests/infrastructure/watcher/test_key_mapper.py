from pathlib import Path

import pytest

from edelrep.infrastructure.watcher.key_mapper import (
    EntityKind,
    classify,
    is_temp_atomic_write,
    path_to_key,
)


def test_path_to_key_returns_posix_relative(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    abs_path = root / "12345" / "_vehicle.json"
    abs_path.parent.mkdir()
    abs_path.touch()
    assert path_to_key(abs_path, root) == "12345/_vehicle.json"


def test_path_to_key_root_itself_returns_empty_string(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    assert path_to_key(root, root) == ""


def test_path_to_key_outside_root_returns_none(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    other = tmp_path / "other_dir" / "file.txt"
    assert path_to_key(other, root) is None


_VID = "01J9TGZP6X2K0V3W7Y8Z4QFFFF"


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (f"{_VID}/_vehicle.json", EntityKind.VEHICLE),
        (f"{_VID}/2026-04-15__brakes/_repair.json", EntityKind.REPAIR),
        (
            f"{_VID}/2026-04-15__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg",
            EntityKind.IMAGE,
        ),
        (
            f"{_VID}/2026-04-15__brakes/_thumbs/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg",
            EntityKind.THUMBNAIL,
        ),
        ("_system/inbox/foo.eml", EntityKind.IGNORED),
        (f"{_VID}/random.txt", EntityKind.IGNORED),
        # Legacy registration-number keys no longer match — must be IGNORED:
        ("12345/_vehicle.json", EntityKind.IGNORED),
    ],
)
def test_classify(key: str, expected: EntityKind) -> None:
    assert classify(key) is expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("_vehicle.json.tmp.deadbeef", True),
        ("0001.jpg.tmp.cafe1234", True),
        ("_vehicle.json", False),
        ("0001.jpg", False),
    ],
)
def test_is_temp_atomic_write(filename: str, expected: bool) -> None:
    assert is_temp_atomic_write(Path(filename)) is expected
