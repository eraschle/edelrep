import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from edelrep.cli.main import _cmd_watch, main
from edelrep.domain.entities import Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import FilesystemVehicleRepository
from edelrep.infrastructure.storage import LocalFilesystemBackend


def _seed_vehicle(storage_root: Path) -> None:
    backend = LocalFilesystemBackend(storage_root)
    repo = FilesystemVehicleRepository(backend)
    repo.save(
        Vehicle(
            id=VehicleId("12345"),
            vin="X",
            description="x",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )


def test_reindex_command_succeeds(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    storage = tmp_path / "store"
    storage.mkdir()
    _seed_vehicle(storage)
    index_path = tmp_path / "index.db"

    exit_code = main(["reindex", "--storage-root", str(storage), "--index-path", str(index_path)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "vehicles_indexed=1" in captured.out
    assert index_path.is_file()


def test_no_args_prints_help_and_exits_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])
    assert exit_code != 0


def test_unknown_command_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as info:
        main(["totally-unknown-cmd"])
    assert info.value.code != 0


def test_reindex_creates_index_directory(tmp_path: Path) -> None:
    storage = tmp_path / "store"
    storage.mkdir()
    _seed_vehicle(storage)
    nested_index = tmp_path / "deep" / "nested" / "index.db"

    exit_code = main(["reindex", "--storage-root", str(storage), "--index-path", str(nested_index)])
    assert exit_code == 0
    assert nested_index.is_file()


def test_watch_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["watch", "--help"])
    assert info.value.code == 0


def test_watch_with_pre_set_stop_event_returns_immediately(tmp_path: Path) -> None:
    storage = tmp_path / "store"
    storage.mkdir()
    index_path = tmp_path / "index.db"
    stop_event = threading.Event()
    stop_event.set()  # pre-set so the wait() returns immediately

    code = _cmd_watch(storage, index_path, stop_event=stop_event)
    assert code == 0
    assert index_path.is_file()


def test_watch_prints_drift_warning_when_drifted(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    storage = tmp_path / "store"
    storage.mkdir()
    # Seed a vehicle BEFORE the index exists; index is fresh so drift_detected = True.
    backend = LocalFilesystemBackend(storage)
    FilesystemVehicleRepository(backend).save(
        Vehicle(
            id=VehicleId("12345"),
            vin="X",
            description="x",
            created_at=datetime(2026, 5, 3, tzinfo=UTC),
        )
    )

    index_path = tmp_path / "index.db"
    stop_event = threading.Event()
    stop_event.set()
    code = _cmd_watch(storage, index_path, stop_event=stop_event)
    assert code == 0
    captured = capsys.readouterr()
    assert "drifted" in captured.out
