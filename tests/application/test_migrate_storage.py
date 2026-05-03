import shutil
from pathlib import Path

import pytest

from edelrep.application.migrate_storage import (
    MigrateStorageUseCase,
    MigrationStats,
)


def test_copies_empty_directory(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"
    use_case = MigrateStorageUseCase()
    stats = use_case.execute(source_root=src, target_root=dst)
    assert isinstance(stats, MigrationStats)
    assert stats.files_copied == 0
    assert dst.is_dir()


def test_copies_nested_files(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "12345").mkdir()
    (src / "12345" / "_vehicle.json").write_text('{"x": 1}', encoding="utf-8")
    (src / "12345" / "2026-04-15__brakes").mkdir()
    (src / "12345" / "2026-04-15__brakes" / "_repair.json").write_text('{"y": 2}', encoding="utf-8")
    (src / "12345" / "2026-04-15__brakes" / "0001_image.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    dst = tmp_path / "dst"
    use_case = MigrateStorageUseCase()
    stats = use_case.execute(source_root=src, target_root=dst)

    assert stats.files_copied == 3
    assert stats.bytes_copied > 0
    assert (dst / "12345" / "_vehicle.json").read_text() == '{"x": 1}'
    assert (dst / "12345" / "2026-04-15__brakes" / "_repair.json").read_text() == '{"y": 2}'
    assert (dst / "12345" / "2026-04-15__brakes" / "0001_image.jpg").read_bytes() == b"\xff\xd8\xff\xd9"


def test_refuses_existing_non_empty_target(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "existing.txt").write_text("oops")
    use_case = MigrateStorageUseCase()
    with pytest.raises(ValueError, match="not empty"):
        use_case.execute(source_root=src, target_root=dst)


def test_allows_existing_empty_target(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "12345").mkdir()
    (src / "12345" / "_vehicle.json").write_text("{}", encoding="utf-8")
    dst = tmp_path / "dst"
    dst.mkdir()  # exists but empty
    use_case = MigrateStorageUseCase()
    stats = use_case.execute(source_root=src, target_root=dst)
    assert stats.files_copied == 1


def test_raises_when_source_missing(tmp_path: Path) -> None:
    src = tmp_path / "missing"
    dst = tmp_path / "dst"
    use_case = MigrateStorageUseCase()
    with pytest.raises(FileNotFoundError):
        use_case.execute(source_root=src, target_root=dst)


def test_stats_duration_is_positive(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("a")
    dst = tmp_path / "dst"
    use_case = MigrateStorageUseCase()
    stats = use_case.execute(source_root=src, target_root=dst)
    assert stats.duration_seconds >= 0


def test_count_mismatch_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If post-copy count differs (simulated), the use case raises."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("a")
    (src / "b.txt").write_text("b")
    dst = tmp_path / "dst"

    real_copytree = shutil.copytree

    def lossy_copytree(s: Path, d: Path, **kwargs: object) -> Path:
        result = real_copytree(s, d, **kwargs)  # type: ignore[arg-type]
        # Simulate a missing file in target.
        (d / "a.txt").unlink()
        return result

    monkeypatch.setattr(shutil, "copytree", lossy_copytree)
    use_case = MigrateStorageUseCase()
    with pytest.raises(RuntimeError, match="verification failed"):
        use_case.execute(source_root=src, target_root=dst)
