import threading
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from ulid import ULID

from edelrep.cli.main import _cmd_watch, main
from edelrep.domain.entities import Vehicle
from edelrep.infrastructure.filesystem import FilesystemVehicleRepository
from edelrep.infrastructure.storage import LocalFilesystemBackend


def _seed_vehicle(storage_root: Path) -> None:
    backend = LocalFilesystemBackend(storage_root)
    repo = FilesystemVehicleRepository(backend)
    repo.save(
        Vehicle(
            id=ULID(),
            registration_number="12345",
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


def test_watch_command_via_main_dispatches_to_cmd_watch(tmp_path: Path) -> None:
    """Exercise the main() -> _cmd_watch dispatch (lines 59-60) and the
    threading.Event() creation branch when no stop_event is supplied."""
    storage = tmp_path / "store"
    storage.mkdir()
    index_path = tmp_path / "index.db"
    # Patch threading.Event so the wait() returns instantly.
    pre_set = threading.Event()
    pre_set.set()
    with patch("edelrep.cli.main.threading") as mock_threading:
        mock_threading.Event.return_value = pre_set
        code = main(["watch", "--storage-root", str(storage), "--index-path", str(index_path)])
    assert code == 0


def test_watch_prints_drift_warning_when_drifted(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    storage = tmp_path / "store"
    storage.mkdir()
    # Seed a vehicle BEFORE the index exists; index is fresh so drift_detected = True.
    backend = LocalFilesystemBackend(storage)
    FilesystemVehicleRepository(backend).save(
        Vehicle(
            id=ULID(),
            registration_number="12345",
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


def test_serve_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["serve", "--help"])
    assert info.value.code == 0


def test_serve_subparser_accepts_required_args(capsys: pytest.CaptureFixture[str]) -> None:
    """argparse should require --storage-root and --index-path."""
    with pytest.raises(SystemExit) as info:
        main(["serve"])  # no required args
    assert info.value.code != 0


def test_serve_subparser_accepts_email_config(capsys: pytest.CaptureFixture[str]) -> None:
    """argparse should accept --email-config without erroring at parse time."""
    with pytest.raises(SystemExit) as info:
        main(["serve", "--help"])
    assert info.value.code == 0
    captured = capsys.readouterr()
    assert "--email-config" in captured.out


def test_cleanup_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["cleanup", "--help"])
    assert info.value.code == 0


def test_cleanup_on_empty_storage_reports_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    storage = tmp_path / "store"
    storage.mkdir()
    index_path = tmp_path / "index.db"
    code = main(
        [
            "cleanup",
            "--storage-root",
            str(storage),
            "--index-path",
            str(index_path),
        ]
    )
    assert code == 0
    captured = capsys.readouterr()
    assert "vehicles_purged=0" in captured.out
    assert "older_than_days=30" in captured.out


def test_cleanup_purges_aged_soft_deletes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    storage = tmp_path / "store"
    storage.mkdir()
    index_path = tmp_path / "index.db"

    backend = LocalFilesystemBackend(storage)
    repo = FilesystemVehicleRepository(backend)
    aged_id = ULID()
    repo.save(
        Vehicle(
            id=aged_id,
            registration_number="AGED",
            vin=None,
            description=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            deleted_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
    )

    code = main(
        [
            "cleanup",
            "--storage-root",
            str(storage),
            "--index-path",
            str(index_path),
            "--older-than-days",
            "0",
        ]
    )
    assert code == 0
    captured = capsys.readouterr()
    assert "vehicles_purged=1" in captured.out
    assert list(repo.list_all(include_deleted=True)) == []


def test_migrate_storage_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["migrate-storage", "--help"])
    assert info.value.code == 0


def test_migrate_storage_copies_tree(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "12345").mkdir()
    (src / "12345" / "_vehicle.json").write_text("{}", encoding="utf-8")
    dst = tmp_path / "dst"
    code = main(["migrate-storage", "--from", str(src), "--to", str(dst)])
    assert code == 0
    captured = capsys.readouterr()
    assert "files_copied=1" in captured.out


def test_migrate_storage_returns_1_on_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "missing"
    dst = tmp_path / "dst"
    code = main(["migrate-storage", "--from", str(src), "--to", str(dst)])
    assert code == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err
