# Phase 3 — Storage-Backend Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple the three filesystem repositories from `pathlib` by routing all I/O through the Phase 1 `StorageBackend` port. Ship two concrete backends (`LocalFilesystemBackend`, `FsspecBackend`) and prove the repositories work identically against the local filesystem and against fsspec's `memory://` filesystem.

**Architecture:** Concrete backends live under `src/edelrep/infrastructure/storage/`. The `LocalFilesystemBackend` wraps the existing `atomic_write` helpers; the `FsspecBackend` adapts any `fsspec.AbstractFileSystem`. Repository classes lose their `pathlib.Path` field and gain a `StorageBackend` collaborator. All path operations become **key operations** (POSIX-style strings rooted at the storage root), and directory existence checks become sidecar-existence checks.

**Tech Stack:** Python 3.13, `fsspec>=2024.0.0` (new dependency), pytest with parametrized fixtures, hypothesis (existing). No filesystem-specific imports leak into the repos.

**Definition of Done (PLAN.md §12 Phase 3):**
- `LocalFilesystemBackend` and `FsspecBackend` both implement the `StorageBackend` Protocol.
- The three filesystem repositories (`Filesystem{Vehicle,Repair,Image}Repository`) take a `StorageBackend` in `__init__`, not a `Path`.
- Every repository test runs against both backends via a parametrized fixture and passes identically.
- `uv run pyright`, `uv run pytest`, `uv run ruff check .` all green.
- Coverage stays ≥ 95% overall; every new file ≥ 90%.
- Tag `phase-3-complete`.

**Branch:** `phase-3-storage-backend` (off `master` at `b6b84df`).

---

## File Structure

**Created:**

```
src/edelrep/infrastructure/storage/
├── __init__.py                        # re-exports both backends + Factory
├── local_filesystem.py                # LocalFilesystemBackend
├── fsspec_backend.py                  # FsspecBackend
└── factory.py                         # build_storage_backend(config)

tests/infrastructure/storage/
├── __init__.py
├── conftest.py                        # all_backends parametrized fixture
├── test_local_filesystem.py
├── test_fsspec_backend.py
├── test_factory.py
└── test_protocol_compliance.py        # both backends satisfy StorageBackend
```

**Modified:**

```
pyproject.toml                          # add fsspec dependency
src/edelrep/infrastructure/filesystem/
├── vehicle_store.py                    # Path → StorageBackend
├── repair_store.py                     # Path → StorageBackend
├── image_store.py                      # Path → StorageBackend
└── __init__.py                         # no API change; just keep re-exports
tests/infrastructure/filesystem/
├── conftest.py                         # add backend fixture parametrization
├── test_vehicle_store.py               # use backend fixture instead of storage_root
├── test_repair_store.py                # ditto
├── test_image_store.py                 # ditto
└── test_example_roundtrip.py           # parametrize over both backends
```

**Unchanged:** Domain layer, `layout.py`, `atomic_write.py`, `json_codec.py`, `sidecar.py`. The library layer remains backend-agnostic — it deals with paths and bytes, not with key-based storage. The repos translate between the two.

---

## Design Notes

### Path-to-Key Translation

The Phase 2 repos used `Path` objects throughout. Phase 3 expresses every operation as a string key relative to the storage root. The mapping from Phase 2 paths to Phase 3 keys:

| Phase 2 (Path) | Phase 3 (key) |
|---|---|
| `root / "12345" / "_vehicle.json"` | `"12345/_vehicle.json"` |
| `root / "12345" / "2026-04-15__brakes" / "_repair.json"` | `"12345/2026-04-15__brakes/_repair.json"` |
| `root / "12345" / "2026-04-15__brakes" / "0001_<ulid>.jpg"` | `"12345/2026-04-15__brakes/0001_<ulid>.jpg"` |
| `root / "12345" / "2026-04-15__brakes" / "_thumbs" / "0001_<ulid>.jpg"` | `"12345/2026-04-15__brakes/_thumbs/0001_<ulid>.jpg"` |

`layout.py` gains key-returning helpers (`vehicle_sidecar_key`, `repair_sidecar_key`, etc.) alongside the existing `*_path` helpers. The Path helpers remain — they are the right abstraction inside `LocalFilesystemBackend`. The repos use the key helpers exclusively.

### Eliminated operations

- **`directory.mkdir()`** — gone. Both backends create parents implicitly on write.
- **`directory.is_dir()`** as existence check — replaced by `backend.exists(sidecar_key)`. A "vehicle directory" only exists in the domain sense if its `_vehicle.json` is present.
- **`directory.iterdir()`** — replaced by `backend.list_prefix(prefix)` + suffix-based filtering.

### Key listing semantics

`StorageBackend.list_prefix(prefix)` returns **all keys** below the prefix (transitively, not immediate children). The repos must filter to find items at a specific level. Helpers in `layout.py`:

- `is_vehicle_sidecar_key(key) -> bool` — matches `^[^/]+/_vehicle\.json$` and the prefix doesn't start with `_`.
- `is_repair_sidecar_key(key) -> bool` — matches `^[^/]+/\d{4}-\d{2}-\d{2}__[a-z0-9-]+/_repair\.json$`.
- `is_image_key(key, repair_prefix) -> bool` — under `<repair_prefix>/`, matches `\d{4}_<ulid>.<ext>` directly (not under `_thumbs/`).

### Atomicity

`StorageBackend.write_bytes` documentation already says "Atomically write data to key". The two backends honour this differently:

- **`LocalFilesystemBackend`**: delegates to existing `write_bytes_atomic` (temp file + `Path.replace`).
- **`FsspecBackend`**: passes through to the underlying fsspec filesystem. For `memory://` this is trivially atomic (single-dict update). For network filesystems (S3, WebDAV) atomicity is at the object level (the underlying provider's contract). The backend does **not** add temp-file-and-rename for fsspec because most fsspec implementations don't support a generic rename, and per-provider atomic guarantees are already strong. This is documented in `FsspecBackend`'s docstring.

### Factory

`build_storage_backend(config: dict) -> StorageBackend` interprets a sub-section of `pyproject.toml` (or any equivalent dict):

```toml
[storage]
mode = "local"                        # "local" | "fsspec"
root = "/var/lib/edelrep/data"

[storage.fsspec]
protocol = "memory"                   # any fsspec protocol
options = { ... }                     # passed to fsspec.filesystem()
root = ""                             # prefix inside the fsspec filesystem
```

Validation:
- `mode` must be one of `"local"`, `"fsspec"`. Else `ValueError`.
- For `"local"`: `root` is required; the directory is created if missing.
- For `"fsspec"`: `protocol` and `root` are required; `options` defaults to `{}`.

### Test parametrization

`tests/infrastructure/filesystem/conftest.py` gains a `backend` fixture parametrized over `("local", "memory")`. Existing tests rebind `storage_root` → `backend` and use `backend.write_bytes(key, data)` if they were directly seeding via filesystem (most don't — they use the repo APIs). The `test_example_roundtrip.py` test runs twice: once with the example fixture copied to a tmp directory and read via `LocalFilesystemBackend`, once with the same files seeded into a `memory://` filesystem and read via `FsspecBackend`.

### Renaming considered, deferred

The class names `FilesystemVehicleRepository` etc. are arguably misleading once they accept any `StorageBackend`. Rename candidates: `SidecarVehicleRepository`, `KeyValueVehicleRepository`. Decision: **keep the names for Phase 3**. The "filesystem" prefix describes the *layout convention* (sidecars in subdirectories), not the I/O channel. Renaming would touch 30+ test references for zero functional benefit. If a future phase introduces a non-sidecar repo (e.g., a SQLite-backed `SqlVehicleRepository`), the contrast will be useful.

---

## Task 1: Add fsspec dependency

**Files:** `pyproject.toml`

- [ ] **Step 1: Add `fsspec>=2024.0.0` to `[project] dependencies`**

Edit `pyproject.toml`. Change the `dependencies` list from:

```toml
dependencies = [
    "python-ulid>=3.0.0",
]
```

to:

```toml
dependencies = [
    "fsspec>=2024.0.0",
    "python-ulid>=3.0.0",
]
```

- [ ] **Step 2: Sync**

```bash
uv sync
```

Expected: `Resolved N+1 packages` (fsspec brings in no transitive deps for the `memory://` use case).

- [ ] **Step 3: Smoke check**

```bash
uv run python -c "import fsspec; fs = fsspec.filesystem('memory'); print(type(fs).__name__)"
```

Expected: `MemoryFileSystem`.

- [ ] **Step 4: Tooling gates still green**

```bash
uv run pyright
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

131 tests still passing.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add fsspec for storage-backend abstraction"
```

---

## Task 2: Scaffold the storage subpackage

**Files:**
- Create `src/edelrep/infrastructure/storage/__init__.py` (empty 1-byte marker; will be filled in Task 6)
- Create `tests/infrastructure/storage/__init__.py` (1-byte marker)

- [ ] **Step 1: Create both files (single newline each)**

- [ ] **Step 2: Verify**

```bash
uv run pyright
```

- [ ] **Step 3: Commit**

```bash
git add src/edelrep/infrastructure/storage tests/infrastructure/storage
git commit -m "feat(storage): scaffold storage backend subpackage"
```

---

## Task 3: Add layout key helpers

**Files:**
- Modify: `src/edelrep/infrastructure/filesystem/layout.py`
- Modify: `tests/infrastructure/filesystem/test_layout.py`

The repos need string-key counterparts for the existing path helpers, plus three predicate helpers for filtering `list_prefix` results.

- [ ] **Step 1: Add failing tests**

Append to `tests/infrastructure/filesystem/test_layout.py`:

```python
from edelrep.infrastructure.filesystem.layout import (
    image_key,
    is_image_key,
    is_repair_sidecar_key,
    is_vehicle_sidecar_key,
    repair_sidecar_key,
    thumbnail_key,
    vehicle_sidecar_key,
)


def test_vehicle_sidecar_key() -> None:
    assert vehicle_sidecar_key(VehicleId("12345")) == "12345/_vehicle.json"


def test_repair_sidecar_key() -> None:
    key = repair_sidecar_key(VehicleId("12345"), "2026-04-15__brakes")
    assert key == "12345/2026-04-15__brakes/_repair.json"


def test_image_key_format() -> None:
    uid = ULID.from_str("01J9TGZP6X2K0V3W7Y8Z4QABCD")
    assert image_key(VehicleId("12345"), "2026-04-15__brakes", "0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg") == \
        "12345/2026-04-15__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg"


def test_thumbnail_key_format() -> None:
    assert thumbnail_key(VehicleId("12345"), "2026-04-15__brakes", "0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg") == \
        "12345/2026-04-15__brakes/_thumbs/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg"


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("12345/_vehicle.json", True),
        ("12345/2026-04-15__brakes/_repair.json", False),
        ("_system/inbox/foo.eml", False),
        ("12345/_vehicle.json/extra", False),
        ("12345/", False),
        ("", False),
    ],
)
def test_is_vehicle_sidecar_key(key: str, expected: bool) -> None:
    assert is_vehicle_sidecar_key(key) is expected


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("12345/2026-04-15__brakes/_repair.json", True),
        ("12345/_vehicle.json", False),
        ("12345/2026-04-15__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg", False),
        ("12345/2026-04-15__BRAKES/_repair.json", False),
        ("_system/inbox/_repair.json", False),
    ],
)
def test_is_repair_sidecar_key(key: str, expected: bool) -> None:
    assert is_repair_sidecar_key(key) is expected


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("12345/2026-04-15__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg", True),
        ("12345/2026-04-15__brakes/_thumbs/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg", False),
        ("12345/2026-04-15__brakes/_repair.json", False),
        ("12345/_vehicle.json", False),
        ("12345/2026-04-15__brakes/badname.jpg", False),
    ],
)
def test_is_image_key(key: str, expected: bool) -> None:
    assert is_image_key(key) is expected
```

(Also add `from ulid import ULID` to the existing imports if it's not already there — the test fixture file already imports it from earlier tests.)

- [ ] **Step 2: Verify failing**

- [ ] **Step 3: Implementation**

Append to `src/edelrep/infrastructure/filesystem/layout.py` (after `unique_repair_dir_name`):

```python
_VEHICLE_SIDECAR_KEY_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}/_vehicle\.json$")
_VEHICLE_SIDECAR_PREFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}/")
_REPAIR_SIDECAR_KEY_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}/\d{4}-\d{2}-\d{2}__[a-z0-9-]+/_repair\.json$"
)
_IMAGE_KEY_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}/\d{4}-\d{2}-\d{2}__[a-z0-9-]+/\d{4}_[0-9A-HJKMNP-TV-Z]{26}\.[a-zA-Z0-9]+$"
)


def vehicle_sidecar_key(vehicle_id: VehicleId) -> str:
    return f"{vehicle_id.registration_number}/_vehicle.json"


def repair_sidecar_key(vehicle_id: VehicleId, dir_name: str) -> str:
    return f"{vehicle_id.registration_number}/{dir_name}/_repair.json"


def image_key(vehicle_id: VehicleId, dir_name: str, filename: str) -> str:
    return f"{vehicle_id.registration_number}/{dir_name}/{filename}"


def thumbnail_key(vehicle_id: VehicleId, dir_name: str, filename: str) -> str:
    return f"{vehicle_id.registration_number}/{dir_name}/_thumbs/{filename}"


def is_vehicle_sidecar_key(key: str) -> bool:
    if not _VEHICLE_SIDECAR_KEY_RE.match(key):
        return False
    return not key.startswith("_")


def is_repair_sidecar_key(key: str) -> bool:
    if not _REPAIR_SIDECAR_KEY_RE.match(key):
        return False
    return not key.startswith("_")


def is_image_key(key: str) -> bool:
    return bool(_IMAGE_KEY_RE.match(key))
```

Note: `thumbnail_key` is now an exported function name. The existing `thumbnail_path(repair_dir: Path, image_filename_value: str) -> Path` already exists at module scope. **Rename the existing function to `thumbnail_path`** — it's already named that, so just keep both. The new `thumbnail_key` returns a string; the old `thumbnail_path` returns a `Path`. They serve different layers (backends vs. local-fs internals).

- [ ] **Step 4: Tests pass**

```bash
uv run pytest tests/infrastructure/filesystem/test_layout.py -v
```

Total layout tests rise from 20 to ~31.

- [ ] **Step 5: Gates clean**

- [ ] **Step 6: Commit**

```bash
git add src/edelrep/infrastructure/filesystem/layout.py \
        tests/infrastructure/filesystem/test_layout.py
git commit -m "feat(infra): add string-key helpers and predicates to layout module"
```

---

## Task 4: `LocalFilesystemBackend` (TDD)

**Files:**
- Create: `tests/infrastructure/storage/test_local_filesystem.py`
- Create: `src/edelrep/infrastructure/storage/local_filesystem.py`

- [ ] **Step 1: Failing test**

```python
from collections.abc import Iterable
from pathlib import Path

import pytest

from edelrep.infrastructure.storage.local_filesystem import LocalFilesystemBackend


@pytest.fixture
def backend(tmp_path: Path) -> LocalFilesystemBackend:
    return LocalFilesystemBackend(tmp_path / "store")


def test_write_then_read_round_trip(backend: LocalFilesystemBackend) -> None:
    backend.write_bytes("a/b/c.txt", b"hello")
    assert backend.read_bytes("a/b/c.txt") == b"hello"


def test_write_creates_parent_dirs(backend: LocalFilesystemBackend, tmp_path: Path) -> None:
    backend.write_bytes("nested/deep/file.bin", b"x")
    assert (tmp_path / "store" / "nested" / "deep" / "file.bin").read_bytes() == b"x"


def test_write_overwrites_existing(backend: LocalFilesystemBackend) -> None:
    backend.write_bytes("k", b"old")
    backend.write_bytes("k", b"new")
    assert backend.read_bytes("k") == b"new"


def test_write_is_atomic(backend: LocalFilesystemBackend, monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path as _P

    backend.write_bytes("k", b"original")
    real_replace = _P.replace

    def boom(self: _P, target: str | _P) -> _P:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(_P, "replace", boom)
    with pytest.raises(OSError, match="simulated rename failure"):
        backend.write_bytes("k", b"new")
    monkeypatch.setattr(_P, "replace", real_replace)
    assert backend.read_bytes("k") == b"original"


def test_read_missing_raises_file_not_found(backend: LocalFilesystemBackend) -> None:
    with pytest.raises(FileNotFoundError):
        backend.read_bytes("does/not/exist")


def test_open_read_streams_bytes(backend: LocalFilesystemBackend) -> None:
    backend.write_bytes("k", b"streamed")
    with backend.open_read("k") as stream:
        assert stream.read() == b"streamed"


def test_delete_removes_key(backend: LocalFilesystemBackend) -> None:
    backend.write_bytes("k", b"x")
    assert backend.exists("k")
    backend.delete("k")
    assert not backend.exists("k")


def test_delete_missing_is_noop(backend: LocalFilesystemBackend) -> None:
    backend.delete("never/written")  # no exception


def test_exists(backend: LocalFilesystemBackend) -> None:
    assert not backend.exists("k")
    backend.write_bytes("k", b"x")
    assert backend.exists("k")


def test_list_prefix_recursive(backend: LocalFilesystemBackend) -> None:
    backend.write_bytes("a/b/c.txt", b"")
    backend.write_bytes("a/b/d.txt", b"")
    backend.write_bytes("a/e.txt", b"")
    backend.write_bytes("z.txt", b"")
    assert sorted(backend.list_prefix("a/")) == ["a/b/c.txt", "a/b/d.txt", "a/e.txt"]


def test_list_prefix_empty_prefix(backend: LocalFilesystemBackend) -> None:
    backend.write_bytes("a.txt", b"")
    backend.write_bytes("b/c.txt", b"")
    assert sorted(backend.list_prefix("")) == ["a.txt", "b/c.txt"]


def test_list_prefix_returns_iterable_of_strings(backend: LocalFilesystemBackend) -> None:
    backend.write_bytes("k.txt", b"")
    result: Iterable[str] = backend.list_prefix("")
    listed = list(result)
    assert all(isinstance(k, str) for k in listed)


def test_list_prefix_when_root_missing(tmp_path: Path) -> None:
    b = LocalFilesystemBackend(tmp_path / "never_created")
    assert list(b.list_prefix("")) == []


def test_satisfies_protocol(tmp_path: Path) -> None:
    from edelrep.domain.ports import StorageBackend

    backend: StorageBackend = LocalFilesystemBackend(tmp_path)
    assert isinstance(backend, StorageBackend)
```

- [ ] **Step 2: Verify failing**

- [ ] **Step 3: Implementation**

```python
from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO

from edelrep.infrastructure.filesystem.atomic_write import write_bytes_atomic


class LocalFilesystemBackend:
    """StorageBackend implementation against the local filesystem.

    All keys are POSIX-style strings rooted at the configured directory.
    Writes are atomic via tempfile + replace (see ``atomic_write`` module).
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def _path(self, key: str) -> Path:
        return self._root.joinpath(*key.split("/")) if key else self._root

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def write_bytes(self, key: str, data: bytes) -> None:
        write_bytes_atomic(self._path(key), data)

    def open_read(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list_prefix(self, prefix: str) -> Iterable[str]:
        base = self._path(prefix) if prefix else self._root
        if not self._root.is_dir():
            return
        if prefix and not base.exists():
            return
        # Walk the tree and yield POSIX keys relative to root.
        target = base if prefix and base.is_dir() else self._root
        prefix_check = prefix if prefix.endswith("/") or prefix == "" else f"{prefix}/"
        for path in sorted(target.rglob("*")):
            if not path.is_file():
                continue
            key = path.relative_to(self._root).as_posix()
            if prefix == "" or key.startswith(prefix_check) or key == prefix:
                yield key
```

Note: this implementation is intentionally simple. Performance-critical optimisation belongs in Phase 5 (SQLite index).

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Gates clean**

- [ ] **Step 6: Commit**

```bash
git add src/edelrep/infrastructure/storage/local_filesystem.py \
        tests/infrastructure/storage/test_local_filesystem.py
git commit -m "feat(storage): add LocalFilesystemBackend implementing StorageBackend"
```

---

## Task 5: `FsspecBackend` (TDD)

**Files:**
- Create: `tests/infrastructure/storage/test_fsspec_backend.py`
- Create: `src/edelrep/infrastructure/storage/fsspec_backend.py`

- [ ] **Step 1: Failing test**

```python
from collections.abc import Iterable

import fsspec
import pytest
from fsspec.implementations.memory import MemoryFileSystem

from edelrep.infrastructure.storage.fsspec_backend import FsspecBackend


@pytest.fixture
def backend() -> FsspecBackend:
    fs = fsspec.filesystem("memory")
    # Memory filesystem is a singleton — clear any leftover state from prior tests.
    if isinstance(fs, MemoryFileSystem):
        fs.store.clear()
        fs.pseudo_dirs.clear()
    return FsspecBackend(fs, root="/edelrep-test")


def test_write_then_read_round_trip(backend: FsspecBackend) -> None:
    backend.write_bytes("a/b/c.txt", b"hello")
    assert backend.read_bytes("a/b/c.txt") == b"hello"


def test_write_creates_parents_implicitly(backend: FsspecBackend) -> None:
    backend.write_bytes("nested/deep/file.bin", b"x")
    assert backend.exists("nested/deep/file.bin")


def test_write_overwrites(backend: FsspecBackend) -> None:
    backend.write_bytes("k", b"old")
    backend.write_bytes("k", b"new")
    assert backend.read_bytes("k") == b"new"


def test_read_missing_raises_file_not_found(backend: FsspecBackend) -> None:
    with pytest.raises(FileNotFoundError):
        backend.read_bytes("missing")


def test_open_read(backend: FsspecBackend) -> None:
    backend.write_bytes("k", b"streamed")
    with backend.open_read("k") as stream:
        assert stream.read() == b"streamed"


def test_delete(backend: FsspecBackend) -> None:
    backend.write_bytes("k", b"x")
    backend.delete("k")
    assert not backend.exists("k")


def test_delete_missing_is_noop(backend: FsspecBackend) -> None:
    backend.delete("never/written")


def test_exists(backend: FsspecBackend) -> None:
    assert not backend.exists("k")
    backend.write_bytes("k", b"x")
    assert backend.exists("k")


def test_list_prefix_recursive(backend: FsspecBackend) -> None:
    backend.write_bytes("a/b/c.txt", b"")
    backend.write_bytes("a/b/d.txt", b"")
    backend.write_bytes("a/e.txt", b"")
    backend.write_bytes("z.txt", b"")
    assert sorted(backend.list_prefix("a/")) == ["a/b/c.txt", "a/b/d.txt", "a/e.txt"]


def test_list_prefix_empty_prefix(backend: FsspecBackend) -> None:
    backend.write_bytes("a.txt", b"")
    backend.write_bytes("b/c.txt", b"")
    assert sorted(backend.list_prefix("")) == ["a.txt", "b/c.txt"]


def test_list_prefix_when_root_missing() -> None:
    fs = fsspec.filesystem("memory")
    if isinstance(fs, MemoryFileSystem):
        fs.store.clear()
        fs.pseudo_dirs.clear()
    backend = FsspecBackend(fs, root="/never-created-edelrep")
    assert list(backend.list_prefix("")) == []


def test_satisfies_protocol() -> None:
    from edelrep.domain.ports import StorageBackend

    fs = fsspec.filesystem("memory")
    backend: StorageBackend = FsspecBackend(fs, root="/proto-check")
    assert isinstance(backend, StorageBackend)
```

- [ ] **Step 2: Verify failing**

- [ ] **Step 3: Implementation**

```python
from collections.abc import Iterable
from typing import BinaryIO

import fsspec


class FsspecBackend:
    """StorageBackend implementation backed by any fsspec filesystem.

    The backend prepends ``root`` to every key. Atomicity is delegated to
    the underlying fsspec implementation: ``MemoryFileSystem`` writes are
    trivially atomic; remote backends honour the provider's per-object
    contract (e.g., S3 PUT is atomic at object granularity). No
    temp-file-and-rename emulation is added — most fsspec implementations
    do not support a generic rename.
    """

    def __init__(self, filesystem: fsspec.AbstractFileSystem, root: str) -> None:
        self._fs = filesystem
        self._root = root.rstrip("/")

    def _full(self, key: str) -> str:
        return f"{self._root}/{key}" if key else self._root

    def read_bytes(self, key: str) -> bytes:
        try:
            return self._fs.cat_file(self._full(key))
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise FileNotFoundError(str(exc)) from exc

    def write_bytes(self, key: str, data: bytes) -> None:
        self._fs.pipe_file(self._full(key), data)

    def open_read(self, key: str) -> BinaryIO:
        return self._fs.open(self._full(key), "rb")

    def delete(self, key: str) -> None:
        full = self._full(key)
        if self._fs.exists(full):
            self._fs.rm_file(full)

    def exists(self, key: str) -> bool:
        return bool(self._fs.exists(self._full(key)))

    def list_prefix(self, prefix: str) -> Iterable[str]:
        base = self._full(prefix) if prefix else self._root
        if not self._fs.exists(base) and not self._fs.exists(self._root):
            return
        try:
            entries = self._fs.find(base) if self._fs.exists(base) else []
        except FileNotFoundError:
            return
        for entry in sorted(entries):
            # Strip the root prefix so callers see relative keys.
            if entry == self._root or entry == self._root + "/":
                continue
            relative = entry[len(self._root) + 1 :] if entry.startswith(self._root + "/") else entry
            yield relative
```

Notes:
- `find()` returns absolute paths within the fsspec filesystem; we strip the root prefix.
- `MemoryFileSystem.find()` returns only files (matching POSIX `find`), so directory entries are not yielded — consistent with `list_prefix` semantics.

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Gates clean**

- [ ] **Step 6: Commit**

```bash
git add src/edelrep/infrastructure/storage/fsspec_backend.py \
        tests/infrastructure/storage/test_fsspec_backend.py
git commit -m "feat(storage): add FsspecBackend wrapping any fsspec filesystem"
```

---

## Task 6: Backend factory (TDD)

**Files:**
- Create: `tests/infrastructure/storage/test_factory.py`
- Create: `src/edelrep/infrastructure/storage/factory.py`
- Modify: `src/edelrep/infrastructure/storage/__init__.py`

- [ ] **Step 1: Failing tests**

```python
from pathlib import Path

import pytest

from edelrep.infrastructure.storage.factory import build_storage_backend
from edelrep.infrastructure.storage.fsspec_backend import FsspecBackend
from edelrep.infrastructure.storage.local_filesystem import LocalFilesystemBackend


def test_local_backend(tmp_path: Path) -> None:
    backend = build_storage_backend({"mode": "local", "root": str(tmp_path / "store")})
    assert isinstance(backend, LocalFilesystemBackend)


def test_fsspec_memory_backend() -> None:
    backend = build_storage_backend(
        {"mode": "fsspec", "fsspec": {"protocol": "memory", "root": "/edelrep-factory-test"}}
    )
    assert isinstance(backend, FsspecBackend)


def test_unknown_mode_rejected() -> None:
    with pytest.raises(ValueError, match="mode"):
        build_storage_backend({"mode": "carrier-pigeon", "root": "/x"})


def test_local_requires_root() -> None:
    with pytest.raises(ValueError, match="root"):
        build_storage_backend({"mode": "local"})


def test_fsspec_requires_protocol() -> None:
    with pytest.raises(ValueError, match="protocol"):
        build_storage_backend({"mode": "fsspec", "fsspec": {"root": "/x"}})


def test_fsspec_requires_root() -> None:
    with pytest.raises(ValueError, match="root"):
        build_storage_backend({"mode": "fsspec", "fsspec": {"protocol": "memory"}})


def test_local_creates_root_if_missing(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "store"
    assert not target.exists()
    build_storage_backend({"mode": "local", "root": str(target)})
    assert target.is_dir()
```

- [ ] **Step 2: Verify failing**

- [ ] **Step 3: Implementation**

```python
from pathlib import Path
from typing import Any

import fsspec

from edelrep.domain.ports import StorageBackend
from edelrep.infrastructure.storage.fsspec_backend import FsspecBackend
from edelrep.infrastructure.storage.local_filesystem import LocalFilesystemBackend


def build_storage_backend(config: dict[str, Any]) -> StorageBackend:
    """Construct a StorageBackend from a config dict.

    Schema (see plan §Factory):

    .. code-block:: toml

       [storage]
       mode = "local" | "fsspec"
       root = "..."           # required for "local"

       [storage.fsspec]       # required for "fsspec"
       protocol = "..."
       root = "..."
       options = { ... }
    """
    mode = config.get("mode")
    if mode == "local":
        root = config.get("root")
        if not root:
            raise ValueError("storage.mode=local requires 'root'")
        path = Path(root)
        path.mkdir(parents=True, exist_ok=True)
        return LocalFilesystemBackend(path)
    if mode == "fsspec":
        fs_cfg = config.get("fsspec") or {}
        protocol = fs_cfg.get("protocol")
        if not protocol:
            raise ValueError("storage.mode=fsspec requires fsspec.protocol")
        root = fs_cfg.get("root")
        if not root:
            raise ValueError("storage.mode=fsspec requires fsspec.root")
        options = fs_cfg.get("options") or {}
        fs = fsspec.filesystem(protocol, **options)
        return FsspecBackend(fs, root=root)
    raise ValueError(f"unknown storage mode: {mode!r}")
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Update `src/edelrep/infrastructure/storage/__init__.py`**

```python
from edelrep.infrastructure.storage.factory import build_storage_backend
from edelrep.infrastructure.storage.fsspec_backend import FsspecBackend
from edelrep.infrastructure.storage.local_filesystem import LocalFilesystemBackend

__all__ = [
    "FsspecBackend",
    "LocalFilesystemBackend",
    "build_storage_backend",
]
```

- [ ] **Step 6: Gates clean**

- [ ] **Step 7: Commit**

```bash
git add src/edelrep/infrastructure/storage/factory.py \
        src/edelrep/infrastructure/storage/__init__.py \
        tests/infrastructure/storage/test_factory.py
git commit -m "feat(storage): add backend factory (local/fsspec) and storage package re-exports"
```

---

## Task 7: Protocol-compliance test for both backends

**Files:** Create `tests/infrastructure/storage/test_protocol_compliance.py`

- [ ] **Step 1: Test**

```python
from pathlib import Path

import fsspec

from edelrep.domain.ports import StorageBackend
from edelrep.infrastructure.storage import FsspecBackend, LocalFilesystemBackend


def test_local_backend_satisfies_protocol(tmp_path: Path) -> None:
    backend: StorageBackend = LocalFilesystemBackend(tmp_path)
    assert isinstance(backend, StorageBackend)


def test_fsspec_backend_satisfies_protocol() -> None:
    fs = fsspec.filesystem("memory")
    backend: StorageBackend = FsspecBackend(fs, root="/proto-check-2")
    assert isinstance(backend, StorageBackend)
```

- [ ] **Step 2: Pass**

- [ ] **Step 3: Commit**

```bash
git add tests/infrastructure/storage/test_protocol_compliance.py
git commit -m "test(storage): verify both backends satisfy the StorageBackend protocol"
```

---

## Task 8: Refactor `FilesystemVehicleRepository` to use StorageBackend

**Files:**
- Modify: `src/edelrep/infrastructure/filesystem/vehicle_store.py`
- Modify: `src/edelrep/infrastructure/filesystem/conftest.py` (test conftest — adds backend fixture)
- Modify: `tests/infrastructure/filesystem/test_vehicle_store.py`

- [ ] **Step 1: Add the parametrized `backend` fixture to conftest**

Append to `tests/infrastructure/filesystem/conftest.py`:

```python
import fsspec
from fsspec.implementations.memory import MemoryFileSystem

from edelrep.domain.ports import StorageBackend
from edelrep.infrastructure.storage import FsspecBackend, LocalFilesystemBackend


@pytest.fixture(params=["local", "memory"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[StorageBackend]:
    if request.param == "local":
        yield LocalFilesystemBackend(tmp_path / "store")
    else:
        fs = fsspec.filesystem("memory")
        if isinstance(fs, MemoryFileSystem):
            fs.store.clear()
            fs.pseudo_dirs.clear()
        yield FsspecBackend(fs, root=f"/edelrep-{request.node.nodeid.replace('::', '__')}")
```

- [ ] **Step 2: Refactor the production code**

Replace `src/edelrep/infrastructure/filesystem/vehicle_store.py` with:

```python
import json
from collections.abc import Iterable

from edelrep.domain.entities import Vehicle
from edelrep.domain.exceptions import (
    DomainError,
    DuplicateVehicle,
    InvalidVehicleId,
    SidecarSchemaError,
    VehicleNotFound,
)
from edelrep.domain.ports import StorageBackend
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.json_codec import (
    DomainJSONEncoder,
    parse_aware_datetime,
)
from edelrep.infrastructure.filesystem.layout import (
    is_vehicle_sidecar_key,
    vehicle_sidecar_key,
)
from edelrep.infrastructure.filesystem.sidecar import CURRENT_SCHEMA_VERSION


class FilesystemVehicleRepository:
    """VehicleRepository implementation against any StorageBackend.

    Layout convention is unchanged from Phase 2: ``<reg_no>/_vehicle.json``
    sidecars under the storage root.
    """

    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend

    def get(self, vehicle_id: VehicleId) -> Vehicle:
        key = vehicle_sidecar_key(vehicle_id)
        if not self._backend.exists(key):
            raise VehicleNotFound(vehicle_id.registration_number)
        data = _read_sidecar(self._backend, key)
        return _deserialise(vehicle_id, data)

    def save(self, vehicle: Vehicle) -> None:
        key = vehicle_sidecar_key(vehicle.id)
        if self._backend.exists(key):
            raise DuplicateVehicle(vehicle.id.registration_number)
        _write_sidecar(self._backend, key, _serialise(vehicle))

    def update(self, vehicle: Vehicle) -> None:
        key = vehicle_sidecar_key(vehicle.id)
        if not self._backend.exists(key):
            raise VehicleNotFound(vehicle.id.registration_number)
        _write_sidecar(self._backend, key, _serialise(vehicle))

    def exists(self, vehicle_id: VehicleId) -> bool:
        return self._backend.exists(vehicle_sidecar_key(vehicle_id))

    def list_all(self) -> Iterable[Vehicle]:
        for key in sorted(self._backend.list_prefix("")):
            if not is_vehicle_sidecar_key(key):
                continue
            reg_no = key.split("/", 1)[0]
            try:
                vid = VehicleId(reg_no)
            except InvalidVehicleId:
                continue
            data = _read_sidecar(self._backend, key)
            yield _deserialise(vid, data)


def _serialise(vehicle: Vehicle) -> dict[str, object]:
    return {
        "registration_number": vehicle.id.registration_number,
        "vin": vehicle.vin,
        "description": vehicle.description,
        "created_at": vehicle.created_at,
    }


def _deserialise(vehicle_id: VehicleId, data: dict[str, object]) -> Vehicle:
    created_at_raw = data["created_at"]
    if not isinstance(created_at_raw, str):  # pragma: no cover - defensive; sidecar produces strings
        raise TypeError(f"created_at must be ISO string, got {type(created_at_raw).__name__}")
    return Vehicle(
        id=vehicle_id,
        vin=data.get("vin"),  # type: ignore[arg-type]
        description=data.get("description"),  # type: ignore[arg-type]
        created_at=parse_aware_datetime(created_at_raw),
    )


def _read_sidecar(backend: StorageBackend, key: str) -> dict[str, object]:
    raw_bytes = backend.read_bytes(key)
    raw = json.loads(raw_bytes.decode("utf-8"))
    actual = raw.get("schema_version") if isinstance(raw, dict) else None
    if actual != CURRENT_SCHEMA_VERSION:
        raise SidecarSchemaError(key, expected=CURRENT_SCHEMA_VERSION, actual=actual)
    out = dict(raw)
    out.pop("schema_version", None)
    return out


def _write_sidecar(backend: StorageBackend, key: str, data: dict[str, object]) -> None:
    if "schema_version" in data:
        raise ValueError("caller must not pre-populate schema_version")
    payload = {"schema_version": CURRENT_SCHEMA_VERSION, **data}
    text = json.dumps(payload, cls=DomainJSONEncoder, indent=2, ensure_ascii=False)
    backend.write_bytes(key, (text + "\n").encode("utf-8"))
```

Note: the sidecar I/O is duplicated here (locally `_read_sidecar`/`_write_sidecar` against a backend). The existing `sidecar.py` module is path-based; rather than rewrite it, the repos now call backend-aware private helpers. **Deferred refactor**: a follow-up could move these helpers to `sidecar.py` with both a `Path` and a `StorageBackend` overload. For now, three repo files each define the same two helpers (DRY violation, but limited blast radius and trivially extracted later).

Actually, let's just promote them to `sidecar.py` to avoid the DRY violation. Update `sidecar.py`:

In `src/edelrep/infrastructure/filesystem/sidecar.py`, **append** these two functions (do not remove the existing path-based ones):

```python
from edelrep.domain.ports import StorageBackend


def read_backend_sidecar(backend: StorageBackend, key: str) -> dict[str, object]:
    raw_bytes = backend.read_bytes(key)
    raw = json.loads(raw_bytes.decode("utf-8"))
    actual = raw.get("schema_version") if isinstance(raw, dict) else None
    if actual != CURRENT_SCHEMA_VERSION:
        raise SidecarSchemaError(key, expected=CURRENT_SCHEMA_VERSION, actual=actual)
    out = dict(raw)
    out.pop("schema_version", None)
    return out


def write_backend_sidecar(backend: StorageBackend, key: str, data: dict[str, object]) -> None:
    if "schema_version" in data:
        raise ValueError("caller must not pre-populate schema_version")
    payload = {"schema_version": CURRENT_SCHEMA_VERSION, **data}
    text = json.dumps(payload, cls=DomainJSONEncoder, indent=2, ensure_ascii=False)
    backend.write_bytes(key, (text + "\n").encode("utf-8"))
```

(You'll need to add `from edelrep.infrastructure.filesystem.json_codec import DomainJSONEncoder` to the top of `sidecar.py` if not already there. Add `import json` if missing.)

Then in `vehicle_store.py`, replace the local `_read_sidecar`/`_write_sidecar` definitions with imports:

```python
from edelrep.infrastructure.filesystem.sidecar import (
    read_backend_sidecar,
    write_backend_sidecar,
)
```

And use `read_backend_sidecar(self._backend, key)` / `write_backend_sidecar(self._backend, key, data)`.

- [ ] **Step 3: Update tests**

In `tests/infrastructure/filesystem/test_vehicle_store.py`:

- Remove the `storage_root` parameter from each test signature; replace with `backend: StorageBackend`.
- Replace `repo = FilesystemVehicleRepository(storage_root)` with `repo = FilesystemVehicleRepository(backend)`.
- Tests that create files directly (e.g., `(storage_root / "_system").mkdir()`, `(storage_root / "67890").mkdir()`, `sidecar.write_text(...)`) need to use the backend instead. Helpers:
  - `(storage_root / "_system").mkdir()` → no-op required because `list_all` filters underscore-prefixed key prefixes; instead seed an underscore-prefixed key: `backend.write_bytes("_system/inbox/foo.eml", b"")`. The vehicle list should still skip it.
  - `(storage_root / "67890").mkdir()` (folder without sidecar) → no-op needed; without a `_vehicle.json` key, `list_all` simply doesn't yield 67890. To exercise the "skip dir without sidecar" branch, seed a non-sidecar key under that prefix instead: `backend.write_bytes("67890/random.txt", b"")`.
  - The `test_get_raises_schema_error_on_bad_sidecar` test wrote bad JSON to the file. Replace with `backend.write_bytes("12345/_vehicle.json", b'{"schema_version": 99, "vin": "x"}')`.
- Imports: drop `from pathlib import Path` if Path is no longer referenced in the file.

After the rewrite, every test runs twice (once per backend) due to the parametrized fixture.

- [ ] **Step 4: Gates clean; total tests roughly double for the parametrized vehicle suite (~22 vehicle tests now)**

- [ ] **Step 5: Commit**

```bash
git add src/edelrep/infrastructure/filesystem/vehicle_store.py \
        src/edelrep/infrastructure/filesystem/sidecar.py \
        tests/infrastructure/filesystem/conftest.py \
        tests/infrastructure/filesystem/test_vehicle_store.py
git commit -m "refactor(infra): retrofit FilesystemVehicleRepository onto StorageBackend port"
```

---

## Task 9: Refactor `FilesystemRepairRepository`

**Files:**
- Modify: `src/edelrep/infrastructure/filesystem/repair_store.py`
- Modify: `tests/infrastructure/filesystem/test_repair_store.py`

- [ ] **Step 1: Refactor production code**

Replace `repair_store.py` with the StorageBackend-based version. Key translation patterns:

- Use `vehicle_sidecar_key(vehicle_id)` to check vehicle existence → raise `VehicleNotFound`.
- Use `repair_sidecar_key(vehicle_id, dir_name)` to check duplicate → raise `DuplicateRepair`.
- For `get(repair_id)`: iterate `backend.list_prefix("")`, filter `is_repair_sidecar_key`, parse the key (extract `<reg_no>` and `<dir_name>`), read the sidecar, compare ULIDs.
- For `update(repair)`: same scan, but update at the matching key.
- For `list_for_vehicle(vehicle_id)`: iterate `backend.list_prefix(f"{vehicle_id.registration_number}/")`, filter `is_repair_sidecar_key`.

Implementation:

```python
from collections.abc import Iterable

from ulid import ULID

from edelrep.domain.entities import Repair
from edelrep.domain.exceptions import DuplicateRepair, RepairNotFound, VehicleNotFound
from edelrep.domain.ports import StorageBackend
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.json_codec import (
    parse_aware_datetime,
    parse_date,
    parse_ulid,
)
from edelrep.infrastructure.filesystem.layout import (
    is_repair_sidecar_key,
    repair_dir_name,
    repair_sidecar_key,
    vehicle_sidecar_key,
)
from edelrep.infrastructure.filesystem.sidecar import (
    read_backend_sidecar,
    write_backend_sidecar,
)


class FilesystemRepairRepository:
    """RepairRepository implementation against any StorageBackend."""

    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend

    def get(self, repair_id: ULID) -> Repair:
        for key in self._backend.list_prefix(""):
            if not is_repair_sidecar_key(key):
                continue
            data = read_backend_sidecar(self._backend, key)
            if parse_ulid(str(data["id"])) == repair_id:
                vid = VehicleId(key.split("/", 1)[0])
                return _deserialise(vid, data)
        raise RepairNotFound(repair_id)

    def save(self, repair: Repair) -> None:
        if not self._backend.exists(vehicle_sidecar_key(repair.vehicle_id)):
            raise VehicleNotFound(repair.vehicle_id.registration_number)
        dir_name = repair_dir_name(repair.date, repair.description)
        key = repair_sidecar_key(repair.vehicle_id, dir_name)
        if self._backend.exists(key):
            raise DuplicateRepair(repair.vehicle_id.registration_number, dir_name)
        write_backend_sidecar(self._backend, key, _serialise(repair))

    def update(self, repair: Repair) -> None:
        for key in self._backend.list_prefix(""):
            if not is_repair_sidecar_key(key):
                continue
            data = read_backend_sidecar(self._backend, key)
            if parse_ulid(str(data["id"])) == repair.id and key.split("/", 1)[0] == repair.vehicle_id.registration_number:
                write_backend_sidecar(self._backend, key, _serialise(repair))
                return
        raise RepairNotFound(repair.id)

    def list_for_vehicle(self, vehicle_id: VehicleId) -> Iterable[Repair]:
        prefix = f"{vehicle_id.registration_number}/"
        if not self._backend.exists(vehicle_sidecar_key(vehicle_id)):
            return
        repairs: list[Repair] = []
        for key in self._backend.list_prefix(prefix):
            if not is_repair_sidecar_key(key):
                continue
            data = read_backend_sidecar(self._backend, key)
            repairs.append(_deserialise(vehicle_id, data))
        repairs.sort(key=lambda r: r.date, reverse=True)
        yield from repairs


def _serialise(repair: Repair) -> dict[str, object]:
    return {
        "id": str(repair.id),
        "date": repair.date,
        "description": repair.description,
        "created_at": repair.created_at,
    }


def _deserialise(vehicle_id: VehicleId, data: dict[str, object]) -> Repair:
    return Repair(
        id=parse_ulid(str(data["id"])),
        vehicle_id=vehicle_id,
        date=parse_date(str(data["date"])),
        description=str(data["description"]),
        created_at=parse_aware_datetime(str(data["created_at"])),
    )
```

The previously private `REPAIR_DIR_NAME_RE` is no longer needed here — `is_repair_sidecar_key` does the filtering.

- [ ] **Step 2: Update tests** — same pattern as Task 8: replace `storage_root` with `backend`, replace `_seed_vehicle(root, ...)` calls with the backend equivalent (use `FilesystemVehicleRepository(backend).save(...)`). Replace any `(storage_root / "12345" / "stray.txt").write_text(...)` with `backend.write_bytes("12345/stray.txt", b"noise")`. Replace `(storage_root / "12345" / "not-a-repair").mkdir()` with `backend.write_bytes("12345/not-a-repair/something.txt", b"")` (or just delete the test — `is_repair_sidecar_key` filters it transparently).

- [ ] **Step 3: Gates clean**

- [ ] **Step 4: Commit**

```bash
git add src/edelrep/infrastructure/filesystem/repair_store.py \
        tests/infrastructure/filesystem/test_repair_store.py
git commit -m "refactor(infra): retrofit FilesystemRepairRepository onto StorageBackend port"
```

---

## Task 10: Refactor `FilesystemImageRepository`

**Files:**
- Modify: `src/edelrep/infrastructure/filesystem/image_store.py`
- Modify: `tests/infrastructure/filesystem/test_image_store.py`

- [ ] **Step 1: Refactor production code**

Image repo is the most complex because:
- It writes raw bytes (and optional thumbnails) — already byte-oriented, no changes needed there.
- It reconstructs `Image` entities from filesystem metadata. With a `StorageBackend`, `mtime` and `size` are no longer trivial. Decision: rely on byte length for `size_bytes`, and `uploaded_at = datetime.now(UTC)` at WRITE time (encoded into a hidden sidecar? No — that violates PLAN.md §6 "no per-image sidecar"). Alternative: derive `uploaded_at` from the order of keys (lexicographic) and `datetime.now(UTC)` only when reading freshly written items.

The right move per the constraints: `uploaded_at` becomes "best-effort" — the local backend can use `Path.stat().st_mtime` (extending the port? No), the fsspec backend may or may not. **Decision**: for Phase 3, `uploaded_at` defaults to `datetime.now(UTC)` on read for backends that don't expose mtime. Local backend tests will accept any aware datetime. This is consistent with the Phase 2 documentation that lists Phase 4 reconstruction defaults.

Actually, the simpler and more honest approach: extend the read API to return `(key, size_bytes)` tuples. But that changes the port. **Cleanest**: add a `stat(key) -> StorageStat` method to the port? Out of scope for Phase 3.

**Phase 3 decision**: image listing returns `Image` entities with `uploaded_at = datetime.now(UTC)` (placeholder) and `size_bytes = len(backend.read_bytes(key))`. The placeholder is documented. Phase 5 (SQLite index) will store `uploaded_at` properly at write time.

Implementation:

```python
import mimetypes
import re
from collections.abc import Iterable
from datetime import UTC, datetime

from ulid import ULID

from edelrep.domain.entities import Image, ImageSource
from edelrep.domain.exceptions import ImageNotFound, RepairNotFound
from edelrep.domain.ports import StorageBackend
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.layout import (
    image_filename,
    image_key,
    is_image_key,
    is_repair_sidecar_key,
    thumbnail_key,
)
from edelrep.infrastructure.filesystem.sidecar import read_backend_sidecar

_IMAGE_FILE_RE = re.compile(r"^(\d{4})_([0-9A-HJKMNP-TV-Z]{26})\.([a-zA-Z0-9]+)$")


class FilesystemImageRepository:
    """ImageRepository against any StorageBackend.

    Phase 3 read-time defaults (carried from Phase 2):
    - source = ImageSource.MANUAL (Phase 8 inbox correlation pending)
    - captured_at = None (Phase 4 EXIF parsing pending)
    - uploaded_at = datetime.now(UTC) at read time (no mtime on the
      StorageBackend port; Phase 5 SQLite index will track this).
    """

    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend

    def get(self, image_id: ULID) -> Image:
        for key in self._backend.list_prefix(""):
            if not is_image_key(key):
                continue
            filename = key.rsplit("/", 1)[1]
            match = _IMAGE_FILE_RE.match(filename)
            if match and ULID.from_str(match.group(2)) == image_id:
                repair_id = self._repair_id_for_key(key)
                return self._reconstruct(key, repair_id)
        raise ImageNotFound(image_id)

    def save(
        self,
        image: Image,
        *,
        raw_bytes: bytes,
        thumbnail_bytes: bytes | None = None,
    ) -> None:
        repair_path = self._find_repair_path(image.repair_id)
        if repair_path is None:
            raise RepairNotFound(image.repair_id)
        reg_no, dir_name = repair_path
        existing_keys = list(self._backend.list_prefix(f"{reg_no}/{dir_name}/"))
        existing = sum(
            1
            for k in existing_keys
            if "/" in k and "/" not in k.rsplit("/", 1)[1]
            and _IMAGE_FILE_RE.match(k.rsplit("/", 1)[1])
            and is_image_key(k)
        )
        seq = existing + 1
        parts = image.filename.rsplit(".", 1)
        extension = (parts[1] if len(parts) == 2 and parts[1] else "bin").lower()
        vehicle_id = VehicleId(reg_no)
        name = image_filename(seq=seq, image_id=image.id, extension=extension)
        self._backend.write_bytes(image_key(vehicle_id, dir_name, name), raw_bytes)
        if thumbnail_bytes is not None:
            self._backend.write_bytes(thumbnail_key(vehicle_id, dir_name, name), thumbnail_bytes)

    def list_for_repair(self, repair_id: ULID) -> Iterable[Image]:
        repair_path = self._find_repair_path(repair_id)
        if repair_path is None:
            return
        reg_no, dir_name = repair_path
        keys = sorted(
            k for k in self._backend.list_prefix(f"{reg_no}/{dir_name}/") if is_image_key(k)
        )
        for key in keys:
            yield self._reconstruct(key, repair_id)

    def _find_repair_path(self, repair_id: ULID) -> tuple[str, str] | None:
        for key in self._backend.list_prefix(""):
            if not is_repair_sidecar_key(key):
                continue
            data = read_backend_sidecar(self._backend, key)
            if str(data.get("id")) == str(repair_id):
                reg_no, dir_name, _ = key.split("/", 2)
                return reg_no, dir_name.rsplit("/", 1)[0] if "/" in dir_name else dir_name
        return None

    def _repair_id_for_key(self, image_key_value: str) -> ULID:
        # image_key_value looks like "<reg>/<dir>/<filename>"
        reg_no, dir_name, _ = image_key_value.split("/", 2)
        sidecar_key = f"{reg_no}/{dir_name.rsplit('/', 1)[0]}/_repair.json" if "/" in dir_name else f"{reg_no}/{dir_name}/_repair.json"
        data = read_backend_sidecar(self._backend, sidecar_key)
        return ULID.from_str(str(data["id"]))

    def _reconstruct(self, key: str, repair_id: ULID) -> Image:
        filename = key.rsplit("/", 1)[1]
        match = _IMAGE_FILE_RE.match(filename)
        if match is None:  # pragma: no cover - callers pre-filter on is_image_key
            raise ValueError(f"unexpected image filename: {filename!r}")
        image_id = ULID.from_str(match.group(2))
        thumb_candidate = key.rsplit("/", 1)[0] + "/_thumbs/" + filename
        raw = self._backend.read_bytes(key)
        thumb_key_value = thumb_candidate if self._backend.exists(thumb_candidate) else None
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return Image(
            id=image_id,
            repair_id=repair_id,
            storage_key=key,
            thumbnail_key=thumb_key_value,
            filename=filename,
            mime_type=mime,
            size_bytes=len(raw),
            source=ImageSource.MANUAL,
            uploaded_at=datetime.now(UTC),
            captured_at=None,
        )
```

Note: the helpers `_find_repair_path` / `_repair_id_for_key` need careful path splitting. Above implementation handles the repair-sidecar key format `<reg>/<repair_dir>/_repair.json` — splits give `["<reg>", "<repair_dir>", "_repair.json"]` after `split("/", 2)`. The implementer should add a unit test for `_find_repair_path` if the splitting logic is confusing.

Simpler helper approach: parse the repair sidecar key with a regex.

- [ ] **Step 2: Update tests** — replace `storage_root` with `backend`, drop direct path manipulation. Tests that check `storage_root / "12345" / "..." / "0001_..."` need to inspect `backend.exists(...)` and `backend.list_prefix(...)` instead.

The `test_save_falls_back_to_bin_extension_for_extensionless_filename` assertion that filtered `not p.name.startswith("_")` needs the equivalent: filter `is_image_key(k)` from `backend.list_prefix("12345/2026-04-15__bremsbelage-vorne/")`.

- [ ] **Step 3: Gates clean**

- [ ] **Step 4: Commit**

```bash
git add src/edelrep/infrastructure/filesystem/image_store.py \
        tests/infrastructure/filesystem/test_image_store.py
git commit -m "refactor(infra): retrofit FilesystemImageRepository onto StorageBackend port"
```

---

## Task 11: Update example_roundtrip test for both backends

**Files:**
- Modify: `tests/infrastructure/filesystem/test_example_roundtrip.py`

The fixture is filesystem-only (real .json files on disk). To run against `memory://`, copy the fixture contents into a memory-backed StorageBackend at the start of each parametrized test.

- [ ] **Step 1: Add a `seeded_backend` parametrized fixture inline (or in conftest)**

```python
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import fsspec
import pytest
from fsspec.implementations.memory import MemoryFileSystem

from edelrep.domain.ports import StorageBackend
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.storage import FsspecBackend, LocalFilesystemBackend

FIXTURE = Path(__file__).parent / "fixtures" / "example_storage_root"


def _copy_fixture_into_backend(backend: StorageBackend, source: Path) -> None:
    for path in source.rglob("*"):
        if path.is_file():
            key = path.relative_to(source).as_posix()
            backend.write_bytes(key, path.read_bytes())


@pytest.fixture(params=["local", "memory"])
def seeded_backend(
    request: pytest.FixtureRequest, tmp_path: Path
) -> StorageBackend:
    if request.param == "local":
        target = tmp_path / "storage"
        shutil.copytree(FIXTURE, target)
        return LocalFilesystemBackend(target)
    fs = fsspec.filesystem("memory")
    if isinstance(fs, MemoryFileSystem):
        fs.store.clear()
        fs.pseudo_dirs.clear()
    backend: StorageBackend = FsspecBackend(fs, root="/edelrep-roundtrip")
    _copy_fixture_into_backend(backend, FIXTURE)
    return backend


def test_can_read_vehicle_from_fixture(seeded_backend: StorageBackend) -> None:
    repo = FilesystemVehicleRepository(seeded_backend)
    vehicle = repo.get(VehicleId("12345"))
    assert vehicle.id == VehicleId("12345")
    assert vehicle.vin == "WDB12345TEST"
    assert vehicle.created_at == datetime(2026, 4, 15, 10, 0, tzinfo=UTC)


def test_can_list_repairs_from_fixture(seeded_backend: StorageBackend) -> None:
    repo = FilesystemRepairRepository(seeded_backend)
    repairs = list(repo.list_for_vehicle(VehicleId("12345")))
    assert len(repairs) == 1
    assert repairs[0].description == "Bremsbeläge vorne"


def test_can_list_images_from_fixture(seeded_backend: StorageBackend) -> None:
    repair_repo = FilesystemRepairRepository(seeded_backend)
    image_repo = FilesystemImageRepository(seeded_backend)
    repair = next(iter(repair_repo.list_for_vehicle(VehicleId("12345"))))
    images = list(image_repo.list_for_repair(repair.id))
    assert len(images) == 1
    assert images[0].size_bytes == 4
    assert images[0].thumbnail_key is not None


def test_round_trip_re_save_produces_byte_identical_sidecar(
    seeded_backend: StorageBackend,
) -> None:
    repo = FilesystemVehicleRepository(seeded_backend)
    vehicle = repo.get(VehicleId("12345"))
    sidecar_before = seeded_backend.read_bytes("12345/_vehicle.json")
    repo.update(vehicle)
    sidecar_after = seeded_backend.read_bytes("12345/_vehicle.json")
    assert json.loads(sidecar_before) == json.loads(sidecar_after)
```

- [ ] **Step 2: Gates clean. The 4 roundtrip tests now run twice each (8 cases).**

- [ ] **Step 3: Commit**

```bash
git add tests/infrastructure/filesystem/test_example_roundtrip.py
git commit -m "test(infra): parametrize round-trip acceptance over local + memory backends"
```

---

## Task 12: Phase 3 acceptance + tag

- [ ] **Step 1: Pyright clean**

```bash
uv run pyright
```

- [ ] **Step 2: Pytest with coverage**

```bash
uv run pytest --cov=edelrep --cov-report=term-missing
```

- All tests pass. Expected count: ~190+ (Phase 2's 131 plus Phase 3 backend tests, plus parametrization roughly doubles the repository tests).
- Total coverage ≥ 95%.
- Every file in `src/edelrep/infrastructure/storage/` ≥ 90%.
- Filesystem repos stay ≥ 90%.

- [ ] **Step 3: Ruff clean**

- [ ] **Step 4: Domain framework-import guard**

```bash
! grep -REn "fastapi|sqlalchemy|fsspec|pydantic|httpx|requests" src/edelrep/domain/
```

Pass: exit 0 (no matches in domain layer).

- [ ] **Step 5: Round-trip smoke check against memory://**

```bash
uv run python -c "
import fsspec
from edelrep.infrastructure.storage import FsspecBackend
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.domain.entities import Vehicle, Repair, ImageSource, Image
from edelrep.domain.value_objects import VehicleId
from datetime import UTC, datetime, date
from ulid import ULID

fs = fsspec.filesystem('memory')
backend = FsspecBackend(fs, root='/smoke')

vrepo = FilesystemVehicleRepository(backend)
rrepo = FilesystemRepairRepository(backend)
irepo = FilesystemImageRepository(backend)

v = Vehicle(id=VehicleId('12345'), vin='X', description=None,
            created_at=datetime(2026,5,3,10,0,tzinfo=UTC))
vrepo.save(v)
print('vehicle saved')

rid = ULID()
r = Repair(id=rid, vehicle_id=v.id, date=date(2026,5,3), description='smoke',
           created_at=datetime(2026,5,3,10,0,tzinfo=UTC))
rrepo.save(r)
print('repair saved')

img_id = ULID()
img = Image(id=img_id, repair_id=rid, storage_key='', thumbnail_key=None,
            filename='test.jpg', mime_type='image/jpeg', size_bytes=4,
            source=ImageSource.MANUAL,
            uploaded_at=datetime(2026,5,3,10,0,tzinfo=UTC), captured_at=None)
irepo.save(img, raw_bytes=b'\xff\xd8\xff\xd9')
print('image saved')

read_back = irepo.get(img_id)
print('image read', read_back.size_bytes, 'bytes')
print('OK end-to-end on memory://')
"
```

Expected output ends with `OK end-to-end on memory://`.

- [ ] **Step 6: Tag**

```bash
git tag phase-3-complete
git tag -l
```

Confirm `phase-1-complete`, `phase-2-complete`, `phase-3-complete` all listed.

- [ ] **Step 7: Final commit if needed (clean status → skip)**

---

## Self-Review Notes

- **Spec coverage (PLAN.md §12 Phase 3):** StorageBackend port already present from Phase 1; `FsspecBackend` ✅; factory from config ✅; filesystem stores use StorageBackend ✅; DoD `local FS` and `memory://` both work ✅.
- **Open follow-ups for Phase 4:** the Image repo's `uploaded_at = datetime.now(UTC)` is a placeholder — Phase 5 SQLite index resolves this properly. Use cases (Phase 4) should be written against the StorageBackend-aware repos and use the `build_storage_backend(config)` factory in their composition root.
- **No domain-layer changes** in Phase 3 — repository-port surface is unchanged. Application-layer code from Phase 4 will not be affected by this retrofit beyond the constructor signature swap.
- **DRY**: `read_backend_sidecar` / `write_backend_sidecar` live in `sidecar.py`; the path-based helpers also remain there. Eventually one set may go.
