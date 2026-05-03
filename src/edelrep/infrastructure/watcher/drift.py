import sqlite3
from datetime import datetime
from pathlib import Path


class DriftDetector:
    """Detects whether the index is stale relative to the filesystem.

    Strategy: compare ``meta.last_full_reindex`` against the latest mtime
    of any ``_vehicle.json`` or ``_repair.json`` sidecar under
    ``storage_root``. Returns True if the meta key is missing or any
    sidecar is newer.
    """

    def __init__(self, connection: sqlite3.Connection, storage_root: Path) -> None:
        self._conn = connection
        self._storage_root = storage_root

    def is_drifted(self) -> bool:
        last = self._read_last_reindex()
        if last is None:
            return True
        if not self._storage_root.is_dir():
            return False
        threshold = last.timestamp()
        for name in ("_vehicle.json", "_repair.json"):
            for path in self._storage_root.rglob(name):
                if path.stat().st_mtime > threshold:
                    return True
        return False

    def _read_last_reindex(self) -> datetime | None:
        cur = self._conn.execute("SELECT value FROM meta WHERE key = 'last_full_reindex'")
        row = cur.fetchone()
        if row is None:
            return None
        return datetime.fromisoformat(row[0])
