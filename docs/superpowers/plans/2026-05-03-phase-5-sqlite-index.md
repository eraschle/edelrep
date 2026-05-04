# Phase 5 — SQLite Index Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a SQLite + FTS5 index cache that the SearchVehicleUseCase queries instead of the filesystem. Add a `SqliteIndexProjector` that walks the three filesystem repositories and populates the index. Wrap it in `ReindexUseCase` and expose a CLI entry point `edelrep reindex`. The index is **wegwerfbar** — droppable and reproducible from the filesystem at any time.

**Architecture:** New `src/edelrep/infrastructure/index/` package containing the SQLite schema, connection helpers, the `SqliteSearchIndex` adapter (implements the existing `SearchIndex` Protocol), and the `SqliteIndexProjector` (internal class — not a domain port). New `src/edelrep/application/reindex.py` use case. New `src/edelrep/cli/` package with an `argparse`-driven entry point.

**Tech Stack:** Python 3.13 stdlib `sqlite3` (FTS5 is enabled in CPython's bundled SQLite), `argparse`, hypothesis (existing). No new runtime deps. CPython 3.13 ships SQLite ≥ 3.40 which has FTS5.

**Definition of Done (PLAN.md §12 Phase 5):**
- `SqliteSearchIndex` implements the `SearchIndex` Protocol against a SQLite database with FTS5.
- `SqliteIndexProjector.full_rebuild(vehicle_repo, repair_repo, image_repo)` recreates the index from filesystem state.
- `ReindexUseCase` wraps the projector with the standard application-layer signature.
- `edelrep reindex --storage-root <p> --index-path <p>` works end-to-end.
- Property test: hypothesis-generated repo operations + full_rebuild produce a SQLite database whose counts and FTS5 hits match the input graph.
- Performance test: 1000 vehicles inserted directly, FTS5 search returns < 100 ms (target < 50 ms; allow CI margin).
- `uv run pyright`, `uv run pytest`, `uv run ruff check .` all green.
- Coverage stays ≥ 95% overall; every new file ≥ 90%.
- Tag `phase-5-complete`.

**Branch:** `phase-5-sqlite-index` (off `master` at `16d9eb9`).

---

## File Structure

**Created:**

```
src/edelrep/infrastructure/index/
├── __init__.py                          # re-exports (filled in P5.4)
├── schema.sql                           # SQL DDL, read by connection.py
├── connection.py                        # open_index_database, _ensure_schema, schema_version meta
├── sqlite_search_index.py               # SqliteSearchIndex (implements SearchIndex)
└── projector.py                         # SqliteIndexProjector (full_rebuild + incremental)

src/edelrep/application/
└── reindex.py                           # ReindexUseCase

src/edelrep/cli/
├── __init__.py
└── main.py                              # argparse, `edelrep reindex` command

tests/infrastructure/index/
├── __init__.py
├── conftest.py                          # in-memory SQLite + storage backend fixtures
├── test_connection.py
├── test_sqlite_search_index.py
├── test_projector.py
├── test_property_reindex.py             # hypothesis property test
└── test_performance.py                  # 1000-vehicle FTS5 timing

tests/application/
└── test_reindex.py

tests/cli/
├── __init__.py
└── test_cli.py
```

**Modified:**

```
pyproject.toml                            # add [project.scripts] edelrep = ...
```

**Unchanged:** Domain layer; existing infrastructure (filesystem, storage, exif, search/in_memory); existing use cases.

---

## Design Notes

### Schema (PLAN.md §9, verbatim)

```sql
CREATE TABLE IF NOT EXISTS vehicles (
  registration_number  TEXT PRIMARY KEY,
  vin                  TEXT,
  description          TEXT,
  created_at           TEXT,
  fs_mtime             REAL
);
CREATE INDEX IF NOT EXISTS idx_vehicles_vin ON vehicles(vin);

CREATE VIRTUAL TABLE IF NOT EXISTS vehicles_fts USING fts5(
  registration_number, vin, description,
  content='vehicles', content_rowid='rowid'
);

CREATE TABLE IF NOT EXISTS repairs (
  id                   TEXT PRIMARY KEY,
  registration_number  TEXT NOT NULL,
  date                 TEXT NOT NULL,
  description          TEXT,
  folder_name          TEXT NOT NULL,
  fs_mtime             REAL
);
CREATE INDEX IF NOT EXISTS idx_repairs_vehicle_date
  ON repairs(registration_number, date DESC);

CREATE TABLE IF NOT EXISTS images (
  id            TEXT PRIMARY KEY,
  repair_id     TEXT NOT NULL,
  filename      TEXT NOT NULL,
  thumb_path    TEXT,
  mime_type     TEXT,
  size_bytes    INTEGER,
  exif_taken_at TEXT,
  fs_mtime      REAL
);
CREATE INDEX IF NOT EXISTS idx_images_repair ON images(repair_id);

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);
```

`fs_mtime` is reserved for future drift detection (Phase 6); Phase 5 inserts NULL. `vehicles_fts` uses `content='vehicles'` (external content) — the FTS5 table stores only the indexed terms, not duplicate row data. Triggers must keep `vehicles_fts` in sync with `vehicles`.

Add to schema.sql:

```sql
CREATE TRIGGER IF NOT EXISTS vehicles_fts_ai AFTER INSERT ON vehicles BEGIN
  INSERT INTO vehicles_fts(rowid, registration_number, vin, description)
  VALUES (new.rowid, new.registration_number, new.vin, new.description);
END;

CREATE TRIGGER IF NOT EXISTS vehicles_fts_ad AFTER DELETE ON vehicles BEGIN
  INSERT INTO vehicles_fts(vehicles_fts, rowid, registration_number, vin, description)
  VALUES('delete', old.rowid, old.registration_number, old.vin, old.description);
END;

CREATE TRIGGER IF NOT EXISTS vehicles_fts_au AFTER UPDATE ON vehicles BEGIN
  INSERT INTO vehicles_fts(vehicles_fts, rowid, registration_number, vin, description)
  VALUES('delete', old.rowid, old.registration_number, old.vin, old.description);
  INSERT INTO vehicles_fts(rowid, registration_number, vin, description)
  VALUES (new.rowid, new.registration_number, new.vin, new.description);
END;
```

### Connection module

```python
def open_index_database(path: Path | str) -> sqlite3.Connection:
    """Open (and migrate if needed) a SQLite index database.

    - Path ":memory:" is allowed for tests.
    - On first open, runs schema.sql.
    - On schema_version mismatch, drops all tables and re-applies (V1 policy:
      the index is wegwerfbar, so destructive migration is acceptable).
    - Sets PRAGMA journal_mode=WAL and PRAGMA foreign_keys=ON.
    """
```

`schema_version = 1`. Stored in `meta` table.

### SqliteSearchIndex

Implements the `SearchIndex` Protocol (vehicle-only methods). Internally:
- `search_vehicles(query, limit=20)`: tokenises query (whitespace-split), lowercases, joins with `AND`, suffixes each term with `*`. Runs `SELECT v.* FROM vehicles v JOIN vehicles_fts f ON v.rowid = f.rowid WHERE vehicles_fts MATCH ? LIMIT ?`. If FTS5 syntax errors (e.g., punctuation-only query), falls back to `WHERE registration_number LIKE %q% OR vin LIKE %q% OR description LIKE %q%`.
- `upsert_vehicle(v)`: `INSERT OR REPLACE INTO vehicles ...`. Triggers maintain FTS5.
- `remove_vehicle(vid)`: `DELETE FROM vehicles WHERE registration_number = ?`. Triggers cascade FTS5 cleanup.
- `clear()`: `DELETE FROM vehicles`. Trigger cascades.

Returns `Vehicle` entities (constructed from row data).

### SqliteIndexProjector

Internal class — not a Protocol, not a domain port. Lives in infrastructure.

```python
class SqliteIndexProjector:
    def __init__(self, connection: sqlite3.Connection) -> None: ...

    def full_rebuild(
        self,
        vehicle_repo: VehicleRepository,
        repair_repo: RepairRepository,
        image_repo: ImageRepository,
    ) -> ReindexStats: ...

    # Incremental ops (called by use cases on save/update; not wired in P5,
    # available for Phase 6 watcher and Phase 4 use case integration):
    def upsert_vehicle(self, vehicle: Vehicle) -> None: ...
    def upsert_repair(self, repair: Repair, folder_name: str) -> None: ...
    def upsert_image(self, image: Image) -> None: ...
    def remove_vehicle(self, vehicle_id: VehicleId) -> None: ...
    def remove_repair(self, repair_id: ULID) -> None: ...
    def remove_image(self, image_id: ULID) -> None: ...
```

`ReindexStats` is a frozen dataclass with `vehicles_indexed`, `repairs_indexed`, `images_indexed`, `duration_seconds`.

`full_rebuild` strategy:
1. `BEGIN; DELETE FROM vehicles; DELETE FROM repairs; DELETE FROM images; COMMIT;` (triggers cascade FTS5 cleanup).
2. For each vehicle in `vehicle_repo.list_all()`:
   - INSERT into `vehicles`.
   - For each repair in `repair_repo.list_for_vehicle(vehicle.id)`:
     - INSERT into `repairs` (folder_name = computed via `repair_dir_name`).
     - For each image in `image_repo.list_for_repair(repair.id)`:
       - INSERT into `images`.
3. Update `meta('last_full_reindex', <iso datetime>)`.

All inside one transaction for atomicity.

### ReindexUseCase

```python
class ReindexUseCase:
    def __init__(self, projector: SqliteIndexProjector, ...) -> None: ...
    def execute(self) -> ReindexStats: ...
```

Takes the projector and the three repos. Calls `projector.full_rebuild(...)`. Returns stats.

### CLI

```python
# edelrep/cli/main.py
def main(argv: list[str] | None = None) -> int: ...

# argparse:
#   edelrep reindex --storage-root <path> --index-path <path>
```

Composes:
- `LocalFilesystemBackend(storage_root)` → 3 filesystem repos
- `open_index_database(index_path)` → connection
- `SqliteIndexProjector(connection)` → `ReindexUseCase(projector, repos)`
- Calls `execute()`, prints stats, returns 0.

### Property test

```python
@given(
    vehicle_count=st.integers(1, 4),
    repairs_per_vehicle=st.integers(0, 3),
    images_per_repair=st.integers(0, 3),
)
def test_full_rebuild_matches_input_graph(...):
    # Build N vehicles via LocalFilesystemBackend repos.
    # Run full_rebuild into a fresh in-memory SQLite.
    # Assert: SELECT COUNT(*) FROM vehicles == N.
    # For each known reg_no, FTS5 search hits exactly that vehicle.
    ...
```

Hypothesis caps the dataset small to keep the test fast (each iteration writes real files to tmp_path).

### Performance test

Pure SQL test (no filesystem):
1. Open `:memory:` database via `open_index_database`.
2. `INSERT OR REPLACE INTO vehicles ...` 1000 rows with synthetic data (`reg_no = f"VEH{i:05d}"`, varied descriptions).
3. Time `SearchIndex.search_vehicles("VEH00500", limit=10)` over 100 iterations.
4. Assert mean duration < 100 ms (target 50 ms, but CI may be slow).

---

## Task 1: Scaffold infrastructure/index + cli packages

**Files:**
- Create six 1-byte marker files:
  - `src/edelrep/infrastructure/index/__init__.py`
  - `src/edelrep/cli/__init__.py`
  - `tests/infrastructure/index/__init__.py`
  - `tests/cli/__init__.py`

(Only four — application/reindex.py uses the existing application package; tests/application/__init__.py exists.)

- [ ] **Step 1: Create the four files (1 byte each)**

- [ ] **Step 2: Pyright clean**

- [ ] **Step 3: Commit**

```bash
git add src/edelrep/infrastructure/index src/edelrep/cli \
        tests/infrastructure/index tests/cli
git commit -m "feat: scaffold index and cli subpackages"
```

---

## Task 2: SQL schema + connection module (TDD)

**Files:**
- Create: `src/edelrep/infrastructure/index/schema.sql`
- Create: `src/edelrep/infrastructure/index/connection.py`
- Create: `tests/infrastructure/index/test_connection.py`

- [ ] **Step 1: Write schema.sql**

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS vehicles (
  registration_number  TEXT PRIMARY KEY,
  vin                  TEXT,
  description          TEXT,
  created_at           TEXT,
  fs_mtime             REAL
);
CREATE INDEX IF NOT EXISTS idx_vehicles_vin ON vehicles(vin);

CREATE VIRTUAL TABLE IF NOT EXISTS vehicles_fts USING fts5(
  registration_number, vin, description,
  content='vehicles', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS vehicles_fts_ai AFTER INSERT ON vehicles BEGIN
  INSERT INTO vehicles_fts(rowid, registration_number, vin, description)
  VALUES (new.rowid, new.registration_number, new.vin, new.description);
END;

CREATE TRIGGER IF NOT EXISTS vehicles_fts_ad AFTER DELETE ON vehicles BEGIN
  INSERT INTO vehicles_fts(vehicles_fts, rowid, registration_number, vin, description)
  VALUES('delete', old.rowid, old.registration_number, old.vin, old.description);
END;

CREATE TRIGGER IF NOT EXISTS vehicles_fts_au AFTER UPDATE ON vehicles BEGIN
  INSERT INTO vehicles_fts(vehicles_fts, rowid, registration_number, vin, description)
  VALUES('delete', old.rowid, old.registration_number, old.vin, old.description);
  INSERT INTO vehicles_fts(rowid, registration_number, vin, description)
  VALUES (new.rowid, new.registration_number, new.vin, new.description);
END;

CREATE TABLE IF NOT EXISTS repairs (
  id                   TEXT PRIMARY KEY,
  registration_number  TEXT NOT NULL,
  date                 TEXT NOT NULL,
  description          TEXT,
  folder_name          TEXT NOT NULL,
  fs_mtime             REAL
);
CREATE INDEX IF NOT EXISTS idx_repairs_vehicle_date
  ON repairs(registration_number, date DESC);

CREATE TABLE IF NOT EXISTS images (
  id            TEXT PRIMARY KEY,
  repair_id     TEXT NOT NULL,
  filename      TEXT NOT NULL,
  thumb_path    TEXT,
  mime_type     TEXT,
  size_bytes    INTEGER,
  exif_taken_at TEXT,
  fs_mtime      REAL
);
CREATE INDEX IF NOT EXISTS idx_images_repair ON images(repair_id);

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);
```

- [ ] **Step 2: Failing test**

`tests/infrastructure/index/test_connection.py`:

```python
import sqlite3
from pathlib import Path

import pytest

from edelrep.infrastructure.index.connection import (
    INDEX_SCHEMA_VERSION,
    open_index_database,
)


def test_open_in_memory_creates_schema() -> None:
    conn = open_index_database(":memory:")
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row[0] for row in cur.fetchall()}
    # Includes 'vehicles_fts' related tables; check the user-managed tables exist.
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
    assert cur.fetchone()[0] == 0  # rebuilt; old data dropped
    cur = conn2.execute("SELECT value FROM meta WHERE key = 'schema_version'")
    assert int(cur.fetchone()[0]) == INDEX_SCHEMA_VERSION


def test_wal_mode_set() -> None:
    conn = open_index_database(":memory:")
    # In-memory databases ignore WAL — accept either WAL (file) or memory (in-memory).
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
    assert rows == [("12345",)]
```

- [ ] **Step 3: Verify failing**

```bash
uv run pytest tests/infrastructure/index/test_connection.py -v
```
ModuleNotFoundError on `edelrep.infrastructure.index.connection`.

- [ ] **Step 4: Implementation**

`src/edelrep/infrastructure/index/connection.py`:

```python
import sqlite3
from importlib.resources import files
from pathlib import Path

INDEX_SCHEMA_VERSION = 1
_SCHEMA_SQL = files("edelrep.infrastructure.index").joinpath("schema.sql").read_text(encoding="utf-8")
_USER_TABLES = ("images", "repairs", "vehicles", "meta")


def open_index_database(path: Path | str) -> sqlite3.Connection:
    """Open (and migrate if needed) a SQLite index database.

    - Path ``":memory:"`` is allowed for tests.
    - First open: runs ``schema.sql`` and stamps ``meta.schema_version``.
    - Subsequent opens with mismatched ``schema_version``: drops all user
      tables and re-runs the schema. The index is wegwerfbar per PLAN.md §3.
    - Enables ``PRAGMA journal_mode=WAL`` (file-backed only) and
      ``PRAGMA foreign_keys=ON``.
    """
    conn = sqlite3.connect(path, isolation_level=None)  # autocommit; we BEGIN manually
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if isinstance(path, Path) or (isinstance(path, str) and path != ":memory:"):
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
        return None  # meta table doesn't exist yet
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
```

The `importlib.resources.files` call needs `schema.sql` to be packaged. Verify it works at runtime; if hatchling doesn't include `*.sql` in the wheel by default, add to `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/edelrep"]

[tool.hatch.build.targets.wheel.force-include]
"src/edelrep/infrastructure/index/schema.sql" = "edelrep/infrastructure/index/schema.sql"
```

(Hatchling actually includes non-.py files by default for `packages`. Skip the force-include unless tests fail.)

- [ ] **Step 5: Tests pass**

- [ ] **Step 6: Gates clean**

- [ ] **Step 7: Commit**

```bash
git add src/edelrep/infrastructure/index/schema.sql \
        src/edelrep/infrastructure/index/connection.py \
        tests/infrastructure/index/test_connection.py
git commit -m "feat(index): add SQLite schema with FTS5 and connection helper"
```

If you had to add the hatch `force-include`, also add `pyproject.toml`.

---

## Task 3: SqliteSearchIndex (TDD)

**Files:**
- Create: `tests/infrastructure/index/conftest.py`
- Create: `tests/infrastructure/index/test_sqlite_search_index.py`
- Create: `src/edelrep/infrastructure/index/sqlite_search_index.py`

- [ ] **Step 1: conftest fixture**

`tests/infrastructure/index/conftest.py`:

```python
import sqlite3
from collections.abc import Iterator

import pytest

from edelrep.infrastructure.index.connection import open_index_database


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = open_index_database(":memory:")
    yield connection
    connection.close()
```

- [ ] **Step 2: Failing tests**

`tests/infrastructure/index/test_sqlite_search_index.py`:

```python
import sqlite3
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


def test_satisfies_protocol(conn: sqlite3.Connection) -> None:
    idx: SearchIndex = SqliteSearchIndex(conn)
    assert isinstance(idx, SearchIndex)


def test_empty_query_returns_empty_list(conn: sqlite3.Connection) -> None:
    idx = SqliteSearchIndex(conn)
    idx.upsert_vehicle(_v("12345"))
    assert list(idx.search_vehicles("")) == []


def test_search_by_registration_number(conn: sqlite3.Connection) -> None:
    idx = SqliteSearchIndex(conn)
    idx.upsert_vehicle(_v("12345"))
    idx.upsert_vehicle(_v("99999"))
    results = list(idx.search_vehicles("12345"))
    assert [v.id.registration_number for v in results] == ["12345"]


def test_search_by_vin(conn: sqlite3.Connection) -> None:
    idx = SqliteSearchIndex(conn)
    idx.upsert_vehicle(_v("12345", vin="WDB123ABC"))
    idx.upsert_vehicle(_v("99999", vin="OTHERVIN"))
    results = list(idx.search_vehicles("WDB"))
    assert [v.id.registration_number for v in results] == ["12345"]


def test_search_by_description_token(conn: sqlite3.Connection) -> None:
    idx = SqliteSearchIndex(conn)
    idx.upsert_vehicle(_v("12345", description="Kran 4-achsig"))
    idx.upsert_vehicle(_v("99999", description="Lieferwagen"))
    results = list(idx.search_vehicles("Kran"))
    assert [v.id.registration_number for v in results] == ["12345"]


def test_search_respects_limit(conn: sqlite3.Connection) -> None:
    idx = SqliteSearchIndex(conn)
    for i in range(5):
        idx.upsert_vehicle(_v(f"VEH{i:03d}"))
    results = list(idx.search_vehicles("VEH", limit=3))
    assert len(results) == 3


def test_upsert_replaces_existing(conn: sqlite3.Connection) -> None:
    idx = SqliteSearchIndex(conn)
    idx.upsert_vehicle(_v("12345", description="old"))
    idx.upsert_vehicle(_v("12345", description="new"))
    # The new description should be searchable; the old should not.
    new_hits = list(idx.search_vehicles("new"))
    old_hits = list(idx.search_vehicles("old"))
    assert len(new_hits) == 1
    assert len(old_hits) == 0


def test_remove_vehicle(conn: sqlite3.Connection) -> None:
    idx = SqliteSearchIndex(conn)
    vid = VehicleId("12345")
    idx.upsert_vehicle(_v("12345"))
    idx.remove_vehicle(vid)
    assert list(idx.search_vehicles("12345")) == []


def test_remove_missing_is_noop(conn: sqlite3.Connection) -> None:
    idx = SqliteSearchIndex(conn)
    idx.remove_vehicle(VehicleId("never-existed"))


def test_clear(conn: sqlite3.Connection) -> None:
    idx = SqliteSearchIndex(conn)
    idx.upsert_vehicle(_v("12345"))
    idx.upsert_vehicle(_v("99999"))
    idx.clear()
    assert list(idx.search_vehicles("12345")) == []
    assert list(idx.search_vehicles("99999")) == []


def test_search_falls_back_to_like_for_short_queries(conn: sqlite3.Connection) -> None:
    # FTS5 may not index single characters. Verify a short numeric prefix still finds.
    idx = SqliteSearchIndex(conn)
    idx.upsert_vehicle(_v("12345"))
    results = list(idx.search_vehicles("12"))
    assert any(v.id.registration_number == "12345" for v in results)


def test_search_handles_special_characters(conn: sqlite3.Connection) -> None:
    # Punctuation that would break FTS5 syntax must not crash.
    idx = SqliteSearchIndex(conn)
    idx.upsert_vehicle(_v("12345", description="brake-pads"))
    # Hyphen in query should not raise; results may be empty or include the row.
    results = list(idx.search_vehicles("brake-pads"))
    # Should not raise; either FTS hits or LIKE fallback hits.
    assert isinstance(results, list)
```

- [ ] **Step 3: Verify failing**

- [ ] **Step 4: Implementation**

`src/edelrep/infrastructure/index/sqlite_search_index.py`:

```python
import re
import sqlite3
from collections.abc import Iterable
from datetime import datetime

from edelrep.domain.entities import Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.json_codec import parse_aware_datetime

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


class SqliteSearchIndex:
    """SearchIndex implementation backed by a SQLite database with FTS5."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def search_vehicles(self, query: str, limit: int = 20) -> Iterable[Vehicle]:
        if not query.strip():
            return []
        tokens = _TOKEN_RE.findall(query)
        if tokens:
            fts_query = " AND ".join(f"{t}*" for t in tokens)
            try:
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
                return [_row_to_vehicle(row) for row in cur.fetchall()]
            except sqlite3.OperationalError:
                pass  # fall through to LIKE
        # LIKE fallback for queries that have no usable FTS tokens or that
        # produced an FTS5 syntax error.
        like = f"%{query}%"
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
        self._conn.execute(
            "DELETE FROM vehicles WHERE registration_number = ?",
            (vehicle_id.registration_number,),
        )

    def clear(self) -> None:
        self._conn.execute("DELETE FROM vehicles")


def _row_to_vehicle(row: sqlite3.Row) -> Vehicle:
    created_at_raw = row["created_at"]
    created_at: datetime = parse_aware_datetime(created_at_raw) if created_at_raw else datetime.now()
    return Vehicle(
        id=VehicleId(row["registration_number"]),
        vin=row["vin"],
        description=row["description"],
        created_at=created_at,
    )
```

Note: `ON CONFLICT(registration_number) DO UPDATE` is the SQLite UPSERT idiom. It triggers the AFTER UPDATE FTS5 trigger correctly.

- [ ] **Step 5: Tests pass**

If `test_upsert_replaces_existing` fails (FTS5 update trigger not firing on UPSERT), the workaround is `DELETE` then `INSERT` instead of UPSERT. Adjust if needed.

If `test_search_falls_back_to_like_for_short_queries` fails because `12*` tokenises but doesn't match `12345` in FTS5, that's expected — FTS5 prefix `12*` should match. If it doesn't, the LIKE fallback path catches it. The test passes either way.

- [ ] **Step 6: Gates clean**

- [ ] **Step 7: Commit**

```bash
git add tests/infrastructure/index/conftest.py \
        tests/infrastructure/index/test_sqlite_search_index.py \
        src/edelrep/infrastructure/index/sqlite_search_index.py
git commit -m "feat(index): add SqliteSearchIndex with FTS5 + LIKE fallback"
```

---

## Task 4: SqliteIndexProjector (TDD)

**Files:**
- Create: `tests/infrastructure/index/test_projector.py`
- Create: `src/edelrep/infrastructure/index/projector.py`
- Modify: `src/edelrep/infrastructure/index/__init__.py`

- [ ] **Step 1: Failing tests**

`tests/infrastructure/index/test_projector.py`:

```python
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ulid import ULID

from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.index.projector import (
    ReindexStats,
    SqliteIndexProjector,
)
from edelrep.infrastructure.storage import LocalFilesystemBackend


@pytest.fixture
def storage_repos(tmp_path: Path) -> tuple[
    FilesystemVehicleRepository, FilesystemRepairRepository, FilesystemImageRepository
]:
    backend = LocalFilesystemBackend(tmp_path / "store")
    return (
        FilesystemVehicleRepository(backend),
        FilesystemRepairRepository(backend),
        FilesystemImageRepository(backend),
    )


def _vehicle(reg: str = "12345") -> Vehicle:
    return Vehicle(
        id=VehicleId(reg),
        vin=f"VIN-{reg}",
        description=f"Vehicle {reg}",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _repair(vehicle_id: VehicleId, *, day: int = 1) -> Repair:
    return Repair(
        id=ULID(),
        vehicle_id=vehicle_id,
        date=date(2026, 5, day),
        description=f"repair {day}",
        created_at=datetime(2026, 5, day, tzinfo=UTC),
    )


def test_full_rebuild_empty_storage(conn: sqlite3.Connection, storage_repos) -> None:
    vrepo, rrepo, irepo = storage_repos
    projector = SqliteIndexProjector(conn)
    stats = projector.full_rebuild(vrepo, rrepo, irepo)
    assert isinstance(stats, ReindexStats)
    assert stats.vehicles_indexed == 0
    assert stats.repairs_indexed == 0
    assert stats.images_indexed == 0
    cur = conn.execute("SELECT COUNT(*) FROM vehicles")
    assert cur.fetchone()[0] == 0


def test_full_rebuild_indexes_vehicles(conn: sqlite3.Connection, storage_repos) -> None:
    vrepo, rrepo, irepo = storage_repos
    vrepo.save(_vehicle("12345"))
    vrepo.save(_vehicle("67890"))
    projector = SqliteIndexProjector(conn)
    stats = projector.full_rebuild(vrepo, rrepo, irepo)
    assert stats.vehicles_indexed == 2
    cur = conn.execute("SELECT registration_number FROM vehicles ORDER BY registration_number")
    assert [r[0] for r in cur.fetchall()] == ["12345", "67890"]


def test_full_rebuild_indexes_repairs(conn: sqlite3.Connection, storage_repos) -> None:
    vrepo, rrepo, irepo = storage_repos
    v = _vehicle("12345")
    vrepo.save(v)
    rrepo.save(_repair(v.id, day=1))
    rrepo.save(_repair(v.id, day=2))
    projector = SqliteIndexProjector(conn)
    stats = projector.full_rebuild(vrepo, rrepo, irepo)
    assert stats.repairs_indexed == 2
    cur = conn.execute("SELECT COUNT(*) FROM repairs WHERE registration_number = '12345'")
    assert cur.fetchone()[0] == 2


def test_full_rebuild_drops_existing_data(conn: sqlite3.Connection, storage_repos) -> None:
    vrepo, rrepo, irepo = storage_repos
    vrepo.save(_vehicle("12345"))
    projector = SqliteIndexProjector(conn)
    projector.full_rebuild(vrepo, rrepo, irepo)
    # Now remove the vehicle file and rebuild — the index row should disappear.
    import shutil
    # Get the storage_root from the backend.
    storage_root = vrepo._backend._root  # type: ignore[attr-defined]
    shutil.rmtree(storage_root / "12345")
    stats = projector.full_rebuild(vrepo, rrepo, irepo)
    assert stats.vehicles_indexed == 0
    cur = conn.execute("SELECT COUNT(*) FROM vehicles")
    assert cur.fetchone()[0] == 0


def test_full_rebuild_records_last_full_reindex_meta(conn: sqlite3.Connection, storage_repos) -> None:
    vrepo, rrepo, irepo = storage_repos
    projector = SqliteIndexProjector(conn)
    projector.full_rebuild(vrepo, rrepo, irepo)
    cur = conn.execute("SELECT value FROM meta WHERE key = 'last_full_reindex'")
    row = cur.fetchone()
    assert row is not None
    # ISO datetime
    parsed = datetime.fromisoformat(row[0])
    assert parsed.tzinfo is not None


def test_upsert_vehicle_individual(conn: sqlite3.Connection) -> None:
    projector = SqliteIndexProjector(conn)
    projector.upsert_vehicle(_vehicle("12345"))
    cur = conn.execute("SELECT registration_number FROM vehicles")
    assert cur.fetchone()[0] == "12345"


def test_remove_vehicle_individual(conn: sqlite3.Connection) -> None:
    projector = SqliteIndexProjector(conn)
    projector.upsert_vehicle(_vehicle("12345"))
    projector.remove_vehicle(VehicleId("12345"))
    cur = conn.execute("SELECT COUNT(*) FROM vehicles")
    assert cur.fetchone()[0] == 0
```

- [ ] **Step 2: Verify failing**

- [ ] **Step 3: Implementation**

`src/edelrep/infrastructure/index/projector.py`:

```python
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from ulid import ULID

from edelrep.domain.entities import Image, Repair, Vehicle
from edelrep.domain.ports import (
    ImageRepository,
    RepairRepository,
    VehicleRepository,
)
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.layout import repair_dir_name


@dataclass(frozen=True, slots=True)
class ReindexStats:
    vehicles_indexed: int
    repairs_indexed: int
    images_indexed: int
    duration_seconds: float


class SqliteIndexProjector:
    """Drives full and incremental updates to the SQLite index cache."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def full_rebuild(
        self,
        vehicle_repo: VehicleRepository,
        repair_repo: RepairRepository,
        image_repo: ImageRepository,
    ) -> ReindexStats:
        start = time.perf_counter()
        vehicles_indexed = 0
        repairs_indexed = 0
        images_indexed = 0

        self._conn.execute("BEGIN")
        try:
            self._conn.execute("DELETE FROM images")
            self._conn.execute("DELETE FROM repairs")
            self._conn.execute("DELETE FROM vehicles")
            for vehicle in vehicle_repo.list_all():
                self._insert_vehicle(vehicle)
                vehicles_indexed += 1
                for repair in repair_repo.list_for_vehicle(vehicle.id):
                    self._insert_repair(repair)
                    repairs_indexed += 1
                    for image in image_repo.list_for_repair(repair.id):
                        self._insert_image(image)
                        images_indexed += 1
            self._conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_full_reindex', ?)",
                (datetime.now(UTC).isoformat(),),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return ReindexStats(
            vehicles_indexed=vehicles_indexed,
            repairs_indexed=repairs_indexed,
            images_indexed=images_indexed,
            duration_seconds=time.perf_counter() - start,
        )

    def upsert_vehicle(self, vehicle: Vehicle) -> None:
        self._insert_vehicle(vehicle)

    def upsert_repair(self, repair: Repair) -> None:
        self._insert_repair(repair)

    def upsert_image(self, image: Image) -> None:
        self._insert_image(image)

    def remove_vehicle(self, vehicle_id: VehicleId) -> None:
        self._conn.execute(
            "DELETE FROM vehicles WHERE registration_number = ?",
            (vehicle_id.registration_number,),
        )

    def remove_repair(self, repair_id: ULID) -> None:
        self._conn.execute("DELETE FROM repairs WHERE id = ?", (str(repair_id),))

    def remove_image(self, image_id: ULID) -> None:
        self._conn.execute("DELETE FROM images WHERE id = ?", (str(image_id),))

    def _insert_vehicle(self, vehicle: Vehicle) -> None:
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

    def _insert_repair(self, repair: Repair) -> None:
        folder = repair_dir_name(repair.date, repair.description)
        self._conn.execute(
            """
            INSERT INTO repairs (id, registration_number, date, description, folder_name, fs_mtime)
            VALUES (?, ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                registration_number = excluded.registration_number,
                date = excluded.date,
                description = excluded.description,
                folder_name = excluded.folder_name
            """,
            (
                str(repair.id),
                repair.vehicle_id.registration_number,
                repair.date.isoformat(),
                repair.description,
                folder,
            ),
        )

    def _insert_image(self, image: Image) -> None:
        self._conn.execute(
            """
            INSERT INTO images (id, repair_id, filename, thumb_path, mime_type,
                                size_bytes, exif_taken_at, fs_mtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                repair_id = excluded.repair_id,
                filename = excluded.filename,
                thumb_path = excluded.thumb_path,
                mime_type = excluded.mime_type,
                size_bytes = excluded.size_bytes,
                exif_taken_at = excluded.exif_taken_at
            """,
            (
                str(image.id),
                str(image.repair_id),
                image.filename,
                image.thumbnail_key,
                image.mime_type,
                image.size_bytes,
                image.captured_at.isoformat() if image.captured_at else None,
            ),
        )
```

- [ ] **Step 4: Update `__init__.py`**

```python
from edelrep.infrastructure.index.connection import (
    INDEX_SCHEMA_VERSION,
    open_index_database,
)
from edelrep.infrastructure.index.projector import (
    ReindexStats,
    SqliteIndexProjector,
)
from edelrep.infrastructure.index.sqlite_search_index import SqliteSearchIndex

__all__ = [
    "INDEX_SCHEMA_VERSION",
    "ReindexStats",
    "SqliteIndexProjector",
    "SqliteSearchIndex",
    "open_index_database",
]
```

- [ ] **Step 5: Tests pass + gates clean**

- [ ] **Step 6: Commit**

```bash
git add tests/infrastructure/index/test_projector.py \
        src/edelrep/infrastructure/index/projector.py \
        src/edelrep/infrastructure/index/__init__.py
git commit -m "feat(index): add SqliteIndexProjector with full_rebuild and incremental ops"
```

---

## Task 5: ReindexUseCase (TDD)

**Files:**
- Create: `tests/application/test_reindex.py`
- Create: `src/edelrep/application/reindex.py`

- [ ] **Step 1: Failing tests**

`tests/application/test_reindex.py`:

```python
import sqlite3
from datetime import UTC, date, datetime

import pytest
from ulid import ULID

from edelrep.application.reindex import ReindexUseCase
from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.index.connection import open_index_database
from edelrep.infrastructure.index.projector import (
    ReindexStats,
    SqliteIndexProjector,
)

from .fakes import InMemoryImageRepo, InMemoryRepairRepo, InMemoryVehicleRepo


@pytest.fixture
def conn() -> sqlite3.Connection:
    return open_index_database(":memory:")


def test_reindex_returns_stats(
    conn: sqlite3.Connection,
    vehicle_repo: InMemoryVehicleRepo,
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
) -> None:
    vehicle = Vehicle(
        id=VehicleId("12345"),
        vin="X",
        description="x",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    vehicle_repo.save(vehicle)
    repair_repo.save(
        Repair(
            id=ULID(),
            vehicle_id=vehicle.id,
            date=date(2026, 5, 1),
            description="brakes",
            created_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
    )
    projector = SqliteIndexProjector(conn)
    use_case = ReindexUseCase(projector, vehicle_repo, repair_repo, image_repo)
    stats = use_case.execute()
    assert isinstance(stats, ReindexStats)
    assert stats.vehicles_indexed == 1
    assert stats.repairs_indexed == 1


def test_reindex_empty_storage(
    conn: sqlite3.Connection,
    vehicle_repo: InMemoryVehicleRepo,
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
) -> None:
    projector = SqliteIndexProjector(conn)
    use_case = ReindexUseCase(projector, vehicle_repo, repair_repo, image_repo)
    stats = use_case.execute()
    assert stats.vehicles_indexed == 0
```

- [ ] **Step 2: Verify failing**

- [ ] **Step 3: Implementation**

`src/edelrep/application/reindex.py`:

```python
from edelrep.domain.ports import (
    ImageRepository,
    RepairRepository,
    VehicleRepository,
)
from edelrep.infrastructure.index.projector import (
    ReindexStats,
    SqliteIndexProjector,
)


class ReindexUseCase:
    """Rebuild the SQLite index cache from filesystem state."""

    def __init__(
        self,
        projector: SqliteIndexProjector,
        vehicle_repo: VehicleRepository,
        repair_repo: RepairRepository,
        image_repo: ImageRepository,
    ) -> None:
        self._projector = projector
        self._vehicle_repo = vehicle_repo
        self._repair_repo = repair_repo
        self._image_repo = image_repo

    def execute(self) -> ReindexStats:
        return self._projector.full_rebuild(
            self._vehicle_repo,
            self._repair_repo,
            self._image_repo,
        )
```

Note: this use case imports from `infrastructure.index` (a concrete adapter type). That's a deviation from strict clean architecture (application should depend only on domain ports). However, `SqliteIndexProjector` is intentionally NOT a domain port — it's an internal infrastructure orchestrator with implementation-specific behaviour. The use case wraps it for symmetry with the other use cases. If this becomes a problem in Phase 6, introduce an `IndexProjector` domain Protocol.

- [ ] **Step 4: Update application `__init__.py` to re-export**

Add `ReindexUseCase` and `ReindexStats` to `__all__`.

- [ ] **Step 5: Tests pass + gates clean**

- [ ] **Step 6: Commit**

```bash
git add tests/application/test_reindex.py \
        src/edelrep/application/reindex.py \
        src/edelrep/application/__init__.py
git commit -m "feat(application): add ReindexUseCase wrapping SqliteIndexProjector"
```

---

## Task 6: Property test — random ops vs reindex equivalence

**Files:** `tests/infrastructure/index/test_property_reindex.py`

- [ ] **Step 1: Test**

```python
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st
from ulid import ULID

from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.index.connection import open_index_database
from edelrep.infrastructure.index.projector import SqliteIndexProjector
from edelrep.infrastructure.storage import LocalFilesystemBackend


@settings(deadline=None, max_examples=15)
@given(
    vehicle_count=st.integers(min_value=0, max_value=4),
    repairs_per_vehicle=st.integers(min_value=0, max_value=3),
)
def test_full_rebuild_matches_input_graph(
    tmp_path_factory: pytest.TempPathFactory,
    vehicle_count: int,
    repairs_per_vehicle: int,
) -> None:
    root = tmp_path_factory.mktemp("graph")
    backend = LocalFilesystemBackend(root / "store")
    vrepo = FilesystemVehicleRepository(backend)
    rrepo = FilesystemRepairRepository(backend)
    irepo = FilesystemImageRepository(backend)

    expected_repair_count = vehicle_count * repairs_per_vehicle
    for vi in range(vehicle_count):
        reg = f"VEH{vi:04d}"
        vrepo.save(
            Vehicle(
                id=VehicleId(reg),
                vin=f"VIN-{reg}",
                description=f"Vehicle {reg}",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        for ri in range(repairs_per_vehicle):
            rrepo.save(
                Repair(
                    id=ULID(),
                    vehicle_id=VehicleId(reg),
                    date=date(2026, 1, ri + 1),
                    description=f"repair-{ri}",
                    created_at=datetime(2026, 1, ri + 1, tzinfo=UTC),
                )
            )

    conn = open_index_database(":memory:")
    projector = SqliteIndexProjector(conn)
    stats = projector.full_rebuild(vrepo, rrepo, irepo)

    assert stats.vehicles_indexed == vehicle_count
    assert stats.repairs_indexed == expected_repair_count

    cur = conn.execute("SELECT COUNT(*) FROM vehicles")
    assert cur.fetchone()[0] == vehicle_count
    cur = conn.execute("SELECT COUNT(*) FROM repairs")
    assert cur.fetchone()[0] == expected_repair_count

    # FTS5 sanity: each vehicle's reg_no is searchable.
    for vi in range(vehicle_count):
        reg = f"VEH{vi:04d}"
        cur = conn.execute(
            "SELECT registration_number FROM vehicles_fts WHERE vehicles_fts MATCH ?",
            (f"{reg}*",),
        )
        rows = cur.fetchall()
        assert any(row[0] == reg for row in rows)
```

- [ ] **Step 2: Run**

```bash
uv run pytest tests/infrastructure/index/test_property_reindex.py -v
```

Should pass. Hypothesis runs 15 examples; each writes ~4×3=12 sidecars to tmp_path. Total runtime should be a few seconds.

- [ ] **Step 3: Commit**

```bash
git add tests/infrastructure/index/test_property_reindex.py
git commit -m "test(index): add property test for reindex correctness across random graphs"
```

---

## Task 7: Performance test

**Files:** `tests/infrastructure/index/test_performance.py`

- [ ] **Step 1: Test**

```python
import sqlite3
import time

import pytest

from edelrep.infrastructure.index.connection import open_index_database
from edelrep.infrastructure.index.sqlite_search_index import SqliteSearchIndex

PERF_THRESHOLD_SECONDS = 0.1  # 100 ms (target 50 ms; CI margin)
VEHICLE_COUNT = 1000


@pytest.fixture
def populated_index() -> SqliteSearchIndex:
    conn = open_index_database(":memory:")
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
        "INSERT INTO vehicles (registration_number, vin, description, created_at, fs_mtime) "
        "VALUES (?, ?, ?, ?, NULL)",
        rows,
    )
    conn.execute("COMMIT")
    return SqliteSearchIndex(conn)


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
```

- [ ] **Step 2: Run + verify under threshold**

If it consistently fails on CI but passes locally, raise `PERF_THRESHOLD_SECONDS` to 0.2 and re-run. Document in the test that 50 ms is the actual target per PLAN.md.

- [ ] **Step 3: Commit**

```bash
git add tests/infrastructure/index/test_performance.py
git commit -m "test(index): add 1000-vehicle FTS5 performance gate"
```

---

## Task 8: CLI entry point (TDD)

**Files:**
- Create: `tests/cli/test_cli.py`
- Create: `src/edelrep/cli/main.py`

- [ ] **Step 1: Failing test**

`tests/cli/test_cli.py`:

```python
import io
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

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


def test_unknown_command_exits_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
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
```

- [ ] **Step 2: Verify failing**

- [ ] **Step 3: Implementation**

`src/edelrep/cli/main.py`:

```python
import argparse
import sys
from pathlib import Path

from edelrep.application.reindex import ReindexUseCase
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.index.connection import open_index_database
from edelrep.infrastructure.index.projector import SqliteIndexProjector
from edelrep.infrastructure.storage import LocalFilesystemBackend


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="edelrep")
    sub = parser.add_subparsers(dest="command")

    reindex = sub.add_parser("reindex", help="Rebuild the SQLite index from filesystem")
    reindex.add_argument("--storage-root", type=Path, required=True,
                         help="Root directory of the storage layout")
    reindex.add_argument("--index-path", type=Path, required=True,
                         help="Path to the SQLite index file")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 2

    if args.command == "reindex":
        return _cmd_reindex(args.storage_root, args.index_path)

    parser.error(f"unknown command: {args.command}")
    return 2


def _cmd_reindex(storage_root: Path, index_path: Path) -> int:
    storage_root.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    backend = LocalFilesystemBackend(storage_root)
    vrepo = FilesystemVehicleRepository(backend)
    rrepo = FilesystemRepairRepository(backend)
    irepo = FilesystemImageRepository(backend)

    conn = open_index_database(index_path)
    projector = SqliteIndexProjector(conn)
    use_case = ReindexUseCase(projector, vrepo, rrepo, irepo)
    stats = use_case.execute()

    sys.stdout.write(
        f"reindex complete: vehicles_indexed={stats.vehicles_indexed} "
        f"repairs_indexed={stats.repairs_indexed} "
        f"images_indexed={stats.images_indexed} "
        f"duration={stats.duration_seconds:.3f}s\n"
    )
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Tests pass + gates clean**

- [ ] **Step 5: Commit**

```bash
git add src/edelrep/cli/main.py tests/cli/test_cli.py
git commit -m "feat(cli): add edelrep reindex command"
```

---

## Task 9: pyproject.toml [project.scripts] entry

**Files:** `pyproject.toml`

- [ ] **Step 1: Add scripts table**

After the `[project]` block (or wherever `[project.scripts]` would naturally fit), add:

```toml
[project.scripts]
edelrep = "edelrep.cli.main:main"
```

- [ ] **Step 2: Reinstall**

```bash
uv sync
```

This re-installs the `edelrep` script.

- [ ] **Step 3: Smoke check**

```bash
uv run edelrep --help
```

Expected: argparse help output mentioning the `reindex` command.

- [ ] **Step 4: All gates**

```bash
uv run pyright
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(packaging): expose edelrep CLI as project script"
```

---

## Task 10: Phase 5 acceptance + tag

- [ ] **Step 1: Pyright clean**

- [ ] **Step 2: Pytest with coverage**

```bash
uv run pytest --cov=edelrep --cov-report=term-missing
```

All tests pass. Total coverage ≥ 95%. Every new file ≥ 90%.

- [ ] **Step 3: Ruff clean**

- [ ] **Step 4: Domain framework-import guard**

```bash
! grep -REn "fastapi|sqlalchemy|fsspec|pydantic|httpx|requests|PIL|pillow|sqlite3" src/edelrep/domain/
```

(Added sqlite3.) Domain layer must remain SQL-free.

- [ ] **Step 5: Application framework-import guard**

```bash
! grep -REn "fastapi|sqlalchemy|fsspec|httpx|requests|PIL|pillow" src/edelrep/application/
```

`reindex.py` may import from `infrastructure.index` (acknowledged deviation per Task 5 design note).

- [ ] **Step 6: End-to-end CLI smoke check**

```bash
uv run python - <<'PY'
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from edelrep.domain.entities import Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import FilesystemVehicleRepository
from edelrep.infrastructure.storage import LocalFilesystemBackend

with tempfile.TemporaryDirectory() as td:
    storage = Path(td) / "store"
    storage.mkdir()
    repo = FilesystemVehicleRepository(LocalFilesystemBackend(storage))
    repo.save(Vehicle(id=VehicleId('99999'), vin='X', description=None,
                      created_at=datetime(2026, 5, 3, tzinfo=UTC)))

    index_path = Path(td) / "index.db"
    result = subprocess.run(
        ["uv", "run", "edelrep", "reindex",
         "--storage-root", str(storage),
         "--index-path", str(index_path)],
        capture_output=True, text=True, check=True,
    )
    print(result.stdout.strip())
    assert "vehicles_indexed=1" in result.stdout
    assert index_path.is_file()
print("OK CLI smoke")
PY
```

- [ ] **Step 7: Tag**

```bash
git tag phase-5-complete
git tag -l
```

- [ ] **Step 8: Final commit if needed (typically clean)**

---

## Self-Review Notes

- **Spec coverage (PLAN.md §12 Phase 5):** schema ✅; SqliteSearchIndex with FTS5 ✅; ReindexUseCase ✅; CLI `edelrep reindex` ✅; Projector with incremental ops ✅; property test ✅; performance gate (1000 vehicles, FTS5 search) ✅.
- **Out of scope:** file watcher (Phase 6); web UI (Phase 7); email ingestion (Phase 8); SQLite-backed repair/image listing (Phase 5 stores them but read paths still use filesystem repos).
- **Open follow-ups for Phase 6+:** the projector's incremental methods (`upsert_vehicle`, `upsert_repair`, `upsert_image`, etc.) are not yet wired into the existing use cases. Phase 6 will hook them to `watchdog` events. Phase 4 use cases (UploadImage, etc.) could optionally start calling them at the same time for live consistency without waiting for the watcher — leave that decision for Phase 6.
- **Architectural deviation:** `application/reindex.py` imports `SqliteIndexProjector` from infrastructure. This is acceptable because the projector is intentionally not a port (it's a SQL-specific orchestrator). If a non-SQL projector ever appears, introduce an `IndexProjector` Protocol in `domain/ports/`.
