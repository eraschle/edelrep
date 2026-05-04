import sqlite3
import threading
from datetime import UTC, datetime

from edelrep.domain.entities import Vehicle
from edelrep.domain.ports import SearchIndex
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.index.sqlite_search_index import SqliteSearchIndex


def _v(reg: str, vin: str = "X", description: str = "") -> Vehicle:
    return Vehicle(
        id=VehicleId(reg),
        vin=vin or None,
        description=description or None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_satisfies_protocol(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    idx: SearchIndex = SqliteSearchIndex(conn, lock)
    assert isinstance(idx, SearchIndex)


def test_empty_query_returns_empty_list(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    idx = SqliteSearchIndex(conn, lock)
    idx.upsert_vehicle(_v("12345"))
    assert list(idx.search_vehicles("")) == []


def test_search_by_registration_number(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    idx = SqliteSearchIndex(conn, lock)
    idx.upsert_vehicle(_v("12345"))
    idx.upsert_vehicle(_v("99999"))
    results = list(idx.search_vehicles("12345"))
    assert [v.id.registration_number for v in results] == ["12345"]


def test_search_by_vin(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    idx = SqliteSearchIndex(conn, lock)
    idx.upsert_vehicle(_v("12345", vin="WDB123ABC"))
    idx.upsert_vehicle(_v("99999", vin="OTHERVIN"))
    results = list(idx.search_vehicles("WDB"))
    assert [v.id.registration_number for v in results] == ["12345"]


def test_search_by_description_token(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    idx = SqliteSearchIndex(conn, lock)
    idx.upsert_vehicle(_v("12345", description="Kran 4-achsig"))
    idx.upsert_vehicle(_v("99999", description="Lieferwagen"))
    results = list(idx.search_vehicles("Kran"))
    assert [v.id.registration_number for v in results] == ["12345"]


def test_search_respects_limit(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    idx = SqliteSearchIndex(conn, lock)
    for i in range(5):
        idx.upsert_vehicle(_v(f"VEH{i:03d}"))
    results = list(idx.search_vehicles("VEH", limit=3))
    assert len(results) == 3


def test_upsert_replaces_existing(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    idx = SqliteSearchIndex(conn, lock)
    idx.upsert_vehicle(_v("12345", description="oldterm"))
    idx.upsert_vehicle(_v("12345", description="newterm"))
    new_hits = list(idx.search_vehicles("newterm"))
    old_hits = list(idx.search_vehicles("oldterm"))
    assert len(new_hits) == 1
    assert len(old_hits) == 0


def test_remove_vehicle(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    idx = SqliteSearchIndex(conn, lock)
    vid = VehicleId("12345")
    idx.upsert_vehicle(_v("12345"))
    idx.remove_vehicle(vid)
    assert list(idx.search_vehicles("12345")) == []


def test_remove_missing_is_noop(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    idx = SqliteSearchIndex(conn, lock)
    idx.remove_vehicle(VehicleId("never-existed"))


def test_clear(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    idx = SqliteSearchIndex(conn, lock)
    idx.upsert_vehicle(_v("12345"))
    idx.upsert_vehicle(_v("99999"))
    idx.clear()
    assert list(idx.search_vehicles("12345")) == []
    assert list(idx.search_vehicles("99999")) == []


def test_search_falls_back_to_like_for_short_queries(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    idx = SqliteSearchIndex(conn, lock)
    idx.upsert_vehicle(_v("12345"))
    results = list(idx.search_vehicles("12"))
    assert any(v.id.registration_number == "12345" for v in results)


def test_search_handles_special_characters(conn: sqlite3.Connection, lock: threading.RLock) -> None:
    idx = SqliteSearchIndex(conn, lock)
    idx.upsert_vehicle(_v("12345", description="brake-pads"))
    # Hyphen in query should not raise; results may be empty or include the row.
    results = list(idx.search_vehicles("brake-pads"))
    assert isinstance(results, list)


def test_search_falls_back_to_like_for_fts5_reserved_words(
    conn: sqlite3.Connection, lock: threading.RLock
) -> None:
    idx = SqliteSearchIndex(conn, lock)
    idx.upsert_vehicle(_v("12345"))
    # "OR" is an FTS5 reserved word — the query "OR*" raises sqlite3.OperationalError.
    # The fallback should not raise.
    results = list(idx.search_vehicles("OR"))
    assert isinstance(results, list)
