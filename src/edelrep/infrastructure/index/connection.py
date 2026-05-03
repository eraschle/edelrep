import sqlite3
from importlib.resources import files
from pathlib import Path

INDEX_SCHEMA_VERSION = 1
_SCHEMA_SQL = files("edelrep.infrastructure.index").joinpath("schema.sql").read_text(encoding="utf-8")
_USER_TABLES = ("images", "repairs", "vehicles", "meta")


def open_index_database(path: Path | str) -> sqlite3.Connection:
    """Open (and migrate if needed) a SQLite index database."""
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if isinstance(path, Path) or path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    existing_version = _read_schema_version(conn)
    if existing_version is None:
        _apply_schema(conn)
    elif existing_version != INDEX_SCHEMA_VERSION:
        _drop_all(conn)
        _apply_schema(conn)


def _read_schema_version(conn: sqlite3.Connection) -> int | None:
    try:
        cur = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'")
    except sqlite3.OperationalError:
        return None
    row = cur.fetchone()
    if row is None:
        return None
    return int(row[0])


def _apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQL)
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(INDEX_SCHEMA_VERSION),),
    )


def _drop_all(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS vehicles_fts")
    for table in _USER_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
