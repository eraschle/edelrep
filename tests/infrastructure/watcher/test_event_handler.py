from pathlib import Path
from unittest.mock import MagicMock

from ulid import ULID
from watchdog.events import (
    DirCreatedEvent,
    FileCreatedEvent,
    FileMovedEvent,
)

from edelrep.infrastructure.watcher.event_handler import KeyEventHandler

VID = ULID.from_str("01J9TGZP6X2K0V3W7Y8Z4QFFFF")
VID_OTHER = ULID.from_str("01J9TGZP6X2K0V3W7Y8Z4QEEEE")


def test_file_created_adds_key_to_debouncer(tmp_path: Path) -> None:
    debouncer = MagicMock()
    storage_root = tmp_path / "store"
    storage_root.mkdir()
    handler = KeyEventHandler(storage_root, debouncer)
    abs_path = storage_root / str(VID) / "_vehicle.json"
    abs_path.parent.mkdir()
    abs_path.touch()
    handler.on_any_event(FileCreatedEvent(str(abs_path)))
    debouncer.add.assert_called_once_with(f"{VID!s}/_vehicle.json")


def test_directory_event_is_ignored(tmp_path: Path) -> None:
    debouncer = MagicMock()
    storage_root = tmp_path / "store"
    storage_root.mkdir()
    handler = KeyEventHandler(storage_root, debouncer)
    new_dir = storage_root / str(VID)
    new_dir.mkdir()
    handler.on_any_event(DirCreatedEvent(str(new_dir)))
    debouncer.add.assert_not_called()


def test_temp_atomic_write_is_ignored(tmp_path: Path) -> None:
    debouncer = MagicMock()
    storage_root = tmp_path / "store"
    storage_root.mkdir()
    handler = KeyEventHandler(storage_root, debouncer)
    tmp_file = storage_root / str(VID) / "_vehicle.json.tmp.deadbeef"
    tmp_file.parent.mkdir()
    tmp_file.touch()
    handler.on_any_event(FileCreatedEvent(str(tmp_file)))
    debouncer.add.assert_not_called()


def test_event_outside_root_is_ignored(tmp_path: Path) -> None:
    debouncer = MagicMock()
    storage_root = tmp_path / "store"
    other = tmp_path / "other"
    storage_root.mkdir()
    other.mkdir()
    handler = KeyEventHandler(storage_root, debouncer)
    outside = other / "foo.json"
    outside.touch()
    handler.on_any_event(FileCreatedEvent(str(outside)))
    debouncer.add.assert_not_called()


def test_thumbnail_event_is_ignored(tmp_path: Path) -> None:
    debouncer = MagicMock()
    storage_root = tmp_path / "store"
    storage_root.mkdir()
    handler = KeyEventHandler(storage_root, debouncer)
    thumb = (
        storage_root
        / str(VID)
        / "2026-04-15__brakes"
        / "_thumbs"
        / "0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg"
    )
    thumb.parent.mkdir(parents=True)
    thumb.touch()
    handler.on_any_event(FileCreatedEvent(str(thumb)))
    debouncer.add.assert_not_called()


def test_random_file_is_ignored(tmp_path: Path) -> None:
    debouncer = MagicMock()
    storage_root = tmp_path / "store"
    storage_root.mkdir()
    handler = KeyEventHandler(storage_root, debouncer)
    stray = storage_root / str(VID) / "stray.txt"
    stray.parent.mkdir()
    stray.touch()
    handler.on_any_event(FileCreatedEvent(str(stray)))
    debouncer.add.assert_not_called()


def test_moved_event_adds_both_src_and_dest(tmp_path: Path) -> None:
    debouncer = MagicMock()
    storage_root = tmp_path / "store"
    storage_root.mkdir()
    handler = KeyEventHandler(storage_root, debouncer)
    src = storage_root / str(VID) / "_vehicle.json"
    dest = storage_root / str(VID_OTHER) / "_vehicle.json"
    src.parent.mkdir()
    dest.parent.mkdir()
    src.touch()
    dest.touch()
    handler.on_any_event(FileMovedEvent(str(src), str(dest)))
    calls = {c.args[0] for c in debouncer.add.call_args_list}
    assert calls == {f"{VID!s}/_vehicle.json", f"{VID_OTHER!s}/_vehicle.json"}
