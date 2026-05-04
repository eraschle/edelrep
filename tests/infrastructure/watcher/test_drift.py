import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from edelrep.infrastructure.index.connection import open_index_database
from edelrep.infrastructure.watcher.drift import DriftDetector


def _set_last_reindex(conn: sqlite3.Connection, when: datetime) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_full_reindex', ?)",
        (when.isoformat(),),
    )


def test_returns_drifted_when_meta_missing(tmp_path: Path) -> None:
    conn, lock = open_index_database(":memory:")
    detector = DriftDetector(conn, lock, tmp_path)
    assert detector.is_drifted() is True


def test_returns_not_drifted_for_empty_storage_after_reindex(tmp_path: Path) -> None:
    conn, lock = open_index_database(":memory:")
    _set_last_reindex(conn, datetime.now(UTC))
    storage_root = tmp_path / "store"
    storage_root.mkdir()
    detector = DriftDetector(conn, lock, storage_root)
    assert detector.is_drifted() is False


def test_returns_drifted_when_sidecar_newer_than_last_reindex(tmp_path: Path) -> None:
    conn, lock = open_index_database(":memory:")
    storage_root = tmp_path / "store"
    storage_root.mkdir()
    one_minute_ago = datetime.fromtimestamp(time.time() - 60, tz=UTC)
    _set_last_reindex(conn, one_minute_ago)
    sidecar = storage_root / "12345" / "_vehicle.json"
    sidecar.parent.mkdir()
    sidecar.write_text('{"schema_version": 1}', encoding="utf-8")
    detector = DriftDetector(conn, lock, storage_root)
    assert detector.is_drifted() is True


def test_returns_not_drifted_when_sidecar_older_than_last_reindex(tmp_path: Path) -> None:
    conn, lock = open_index_database(":memory:")
    storage_root = tmp_path / "store"
    storage_root.mkdir()
    sidecar = storage_root / "12345" / "_vehicle.json"
    sidecar.parent.mkdir()
    sidecar.write_text('{"schema_version": 1}', encoding="utf-8")
    time.sleep(0.05)
    _set_last_reindex(conn, datetime.now(UTC))
    detector = DriftDetector(conn, lock, storage_root)
    assert detector.is_drifted() is False


def test_ignores_non_sidecar_files(tmp_path: Path) -> None:
    conn, lock = open_index_database(":memory:")
    storage_root = tmp_path / "store"
    storage_root.mkdir()
    one_minute_ago = datetime.fromtimestamp(time.time() - 60, tz=UTC)
    _set_last_reindex(conn, one_minute_ago)
    (storage_root / "stray.txt").write_text("noise")
    detector = DriftDetector(conn, lock, storage_root)
    assert detector.is_drifted() is False
