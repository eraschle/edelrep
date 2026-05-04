import re
import sqlite3
import threading
from collections.abc import Iterable
from datetime import UTC, datetime

from edelrep.domain.entities import Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.json_codec import parse_aware_datetime

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


class SqliteSearchIndex:
    """SearchIndex implementation backed by a SQLite database with FTS5."""

    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._conn = connection
        self._lock = lock

    def search_vehicles(self, query: str, limit: int = 20) -> Iterable[Vehicle]:
        if not query.strip():
            return []
        tokens = _TOKEN_RE.findall(query)
        if tokens:
            fts_query = " AND ".join(f"{t}*" for t in tokens)
            try:
                with self._lock:
                    cur = self._conn.execute(
                        """
                        SELECT v.registration_number, v.vin, v.description, v.created_at
                        FROM vehicles v
                        JOIN vehicles_fts f ON v.rowid = f.rowid
                        WHERE vehicles_fts MATCH ?
                        LIMIT ?
                        """,
                        (fts_query, limit),
                    )
                    rows = cur.fetchall()
                if rows:
                    return [_row_to_vehicle(row) for row in rows]
            except sqlite3.OperationalError:
                pass
        # LIKE fallback (short queries, FTS5 syntax errors, or zero FTS hits).
        like = f"%{query}%"
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT registration_number, vin, description, created_at
                FROM vehicles
                WHERE registration_number LIKE ?
                   OR (vin IS NOT NULL AND vin LIKE ?)
                   OR (description IS NOT NULL AND description LIKE ?)
                LIMIT ?
                """,
                (like, like, like, limit),
            )
            return [_row_to_vehicle(row) for row in cur.fetchall()]

    def upsert_vehicle(self, vehicle: Vehicle) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO vehicles (registration_number, vin, description, created_at, fs_mtime)
                VALUES (?, ?, ?, ?, NULL)
                ON CONFLICT(registration_number) DO UPDATE SET
                    vin = excluded.vin,
                    description = excluded.description,
                    created_at = excluded.created_at
                """,
                (
                    vehicle.id.registration_number,
                    vehicle.vin,
                    vehicle.description,
                    vehicle.created_at.isoformat(),
                ),
            )

    def remove_vehicle(self, vehicle_id: VehicleId) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM vehicles WHERE registration_number = ?",
                (vehicle_id.registration_number,),
            )

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM vehicles")


def _row_to_vehicle(row: sqlite3.Row) -> Vehicle:
    created_at_raw = row["created_at"]
    created_at: datetime = parse_aware_datetime(created_at_raw) if created_at_raw else datetime.now(UTC)
    return Vehicle(
        id=VehicleId(row["registration_number"]),
        vin=row["vin"],
        description=row["description"],
        created_at=created_at,
    )
