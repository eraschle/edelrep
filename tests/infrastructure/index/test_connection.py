from pathlib import Path

from edelrep.infrastructure.index.connection import (
    INDEX_SCHEMA_VERSION,
    open_index_database,
)


def test_open_in_memory_creates_schema() -> None:
    conn = open_index_database(":memory:")
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cur.fetchall()}
    assert {"vehicles", "repairs", "images", "meta"}.issubset(tables)


def test_open_sets_schema_version_meta() -> None:
    conn = open_index_database(":memory:")
    cur = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'")
    row = cur.fetchone()
    assert row is not None
    assert int(row[0]) == INDEX_SCHEMA_VERSION


def test_open_path_creates_file(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    open_index_database(db_path)
    assert db_path.is_file()


def test_open_existing_database_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    open_index_database(db_path)
    conn2 = open_index_database(db_path)
    cur = conn2.execute("SELECT count(*) FROM meta")
    assert cur.fetchone()[0] >= 1


def test_unknown_schema_version_drops_and_recreates(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    conn = open_index_database(db_path)
    conn.execute(
        "INSERT INTO vehicles (registration_number, vin, description, created_at) "
        "VALUES ('12345', 'X', 'old', '2026-01-01T00:00:00+00:00')"
    )
    conn.execute("UPDATE meta SET value = '99' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()

    conn2 = open_index_database(db_path)
    cur = conn2.execute("SELECT count(*) FROM vehicles")
    assert cur.fetchone()[0] == 0
    cur = conn2.execute("SELECT value FROM meta WHERE key = 'schema_version'")
    assert int(cur.fetchone()[0]) == INDEX_SCHEMA_VERSION


def test_wal_mode_set() -> None:
    conn = open_index_database(":memory:")
    cur = conn.execute("PRAGMA journal_mode")
    mode = cur.fetchone()[0]
    assert mode in ("wal", "memory")


def test_fts5_table_searchable() -> None:
    conn = open_index_database(":memory:")
    conn.execute(
        "INSERT INTO vehicles (registration_number, vin, description, created_at) "
        "VALUES ('12345', 'WDB123', 'Kran 4-achsig', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    cur = conn.execute(
        "SELECT registration_number FROM vehicles_fts WHERE vehicles_fts MATCH ?",
        ("Kran",),
    )
    rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0]["registration_number"] == "12345"
