from datetime import UTC, datetime
from pathlib import Path

import pytest

from edelrep.cli.main import main
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
