import time
from collections.abc import Iterator

import pytest

from edelrep.infrastructure.index.connection import open_index_database
from edelrep.infrastructure.index.sqlite_search_index import SqliteSearchIndex

PERF_THRESHOLD_SECONDS = 0.1  # 100 ms (target 50 ms; CI margin per PLAN.md)
VEHICLE_COUNT = 1000


@pytest.fixture
def populated_index() -> Iterator[SqliteSearchIndex]:
    conn = open_index_database(":memory:")
    try:
        rows = [
            (
                f"VEH{i:05d}",
                f"VIN-{i:08d}",
                f"Description for vehicle number {i}",
                "2026-01-01T00:00:00+00:00",
            )
            for i in range(VEHICLE_COUNT)
        ]
        conn.execute("BEGIN")
        conn.executemany(
            "INSERT INTO vehicles (registration_number, vin, description, created_at, fs_mtime) VALUES (?, ?, ?, ?, NULL)",
            rows,
        )
        conn.execute("COMMIT")
        yield SqliteSearchIndex(conn)
    finally:
        conn.close()


def test_search_under_threshold_for_1000_vehicles(populated_index: SqliteSearchIndex) -> None:
    # Warm up.
    list(populated_index.search_vehicles("VEH00500"))
    # Time 50 iterations.
    start = time.perf_counter()
    for _ in range(50):
        results = list(populated_index.search_vehicles("VEH00500", limit=10))
        assert len(results) >= 1
    elapsed = time.perf_counter() - start
    mean_seconds = elapsed / 50
    assert mean_seconds < PERF_THRESHOLD_SECONDS, (
        f"FTS5 search averaged {mean_seconds * 1000:.2f} ms over {VEHICLE_COUNT} vehicles; "
        f"threshold is {PERF_THRESHOLD_SECONDS * 1000:.0f} ms."
    )
