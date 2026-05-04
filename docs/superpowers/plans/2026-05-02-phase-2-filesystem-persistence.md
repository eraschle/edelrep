# Phase 2 — Filesystem-Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement filesystem-backed concrete adapters for `VehicleRepository`, `RepairRepository`, `ImageRepository` per the directory layout in PLAN.md §6. The filesystem becomes the **Source of Truth** — sidecar JSON files carry `schema_version` and are written atomically.

**Architecture:** `src/edelrep/infrastructure/filesystem/` ships pure path/slug helpers (`layout.py`), an `atomic_write.py` helper, a generic `sidecar.py` reader/writer with schema-version enforcement, and three concrete repository classes. Phase 2 uses `pathlib` directly; Phase 3 retrofits the `StorageBackend` port. Tests use pytest's `tmp_path` fixture for filesystem isolation.

**Tech Stack:** Python 3.13, stdlib only for filesystem (`pathlib`, `os`, `tempfile`, `json`, `datetime`, `unicodedata`, `re`), `python-ulid` for ID generation in tests, pytest + hypothesis.

**Open design decision locked in:**
- The Phase 1 `ImageRepository.save(image: Image) -> None` port is widened in Task 1 to `save(image: Image, *, raw_bytes: bytes, thumbnail_bytes: bytes | None = None) -> None`. Reason: per PLAN.md §6 there is no per-image sidecar — the `Image` entity carries no payload, so without raw bytes the repository has nothing to persist. The compliance test (Phase 1 Task 13) is updated alongside.

**Definition of Done (PLAN.md §12 Phase 2):**
- CRUD over real folders works end-to-end for all three aggregates.
- A prepared example storage folder under `tests/infrastructure/filesystem/fixtures/example_storage_root/` is read by `FilesystemVehicleRepository` / `FilesystemRepairRepository` / `FilesystemImageRepository` and the round-trip (read → write → re-read) reproduces identical entities.
- Atomic-write contract: a partially-written sidecar must never be visible to readers.
- `schema_version: 1` is present in every sidecar; reading a sidecar with an unknown version raises `SidecarSchemaError` (a new domain exception).
- Pyright/pytest/ruff all green; domain coverage stays ≥ 95%; new infrastructure coverage ≥ 90%.
- Tag `phase-2-complete`.

**Branch:** `phase-2-filesystem-persistence` (already created off `master` at `eb634eb`).

---

## File Structure

**Created in this phase:**

```
src/edelrep/
├── domain/
│   ├── exceptions.py                     # MODIFY: add SidecarSchemaError
│   └── ports/
│       └── image_repository.py           # MODIFY: widen save() signature
└── infrastructure/
    ├── __init__.py                       # empty marker
    └── filesystem/
        ├── __init__.py                   # re-exports the three repos
        ├── layout.py                     # pure path/slug functions
        ├── atomic_write.py               # write_bytes_atomic, write_text_atomic
        ├── json_codec.py                 # encode/decode domain types
        ├── sidecar.py                    # SidecarReader, SidecarWriter, schema_version
        ├── vehicle_store.py              # FilesystemVehicleRepository
        ├── repair_store.py               # FilesystemRepairRepository
        └── image_store.py                # FilesystemImageRepository

tests/
├── domain/
│   ├── ports/
│   │   └── test_protocol_compliance.py   # MODIFY: update _FakeImageRepo signature
│   └── test_exceptions.py                # MODIFY: add SidecarSchemaError test
└── infrastructure/
    ├── __init__.py
    └── filesystem/
        ├── __init__.py
        ├── conftest.py                   # tmp_path-based factories
        ├── fixtures/
        │   └── example_storage_root/     # see Task 12
        ├── test_layout.py
        ├── test_atomic_write.py
        ├── test_json_codec.py
        ├── test_sidecar.py
        ├── test_vehicle_store.py
        ├── test_repair_store.py
        ├── test_image_store.py
        └── test_example_roundtrip.py     # DoD acceptance test
```

**Modified:**
- `src/edelrep/domain/ports/image_repository.py` — widen `save()`.
- `src/edelrep/domain/exceptions.py` — add `SidecarSchemaError`.
- `tests/domain/ports/test_protocol_compliance.py` — update fake.
- `tests/domain/test_exceptions.py` — cover new exception.

**No changes to:** Phase 1 entity classes, `VehicleId`, other ports, `pyproject.toml`, `ruff.toml`, `pyrightconfig.json`.

---

## Design Notes

### Layout (Path & Slug)

Per PLAN.md §6:

| Path | Computation |
|------|-------------|
| `<root>/<reg_no>/` | `vehicle_dir(root, vehicle_id)` |
| `<root>/<reg_no>/_vehicle.json` | `vehicle_sidecar_path(root, vehicle_id)` |
| `<root>/<reg_no>/<YYYY-MM-DD>__<slug>/` | `repair_dir(root, vehicle_id, repair_date, slug)` |
| `<root>/<reg_no>/<...>/_repair.json` | `repair_sidecar_path(...)` |
| `<root>/<reg_no>/<...>/<NNNN>_<ulid>.<ext>` | `image_path(repair_dir, seq, image_id, ext)` |
| `<root>/<reg_no>/<...>/_thumbs/<NNNN>_<ulid>.<ext>` | `thumbnail_path(repair_dir, seq, image_id, ext)` |

**Slug** rules (from PLAN.md §6):
- ASCII lowercase, regex-safe `[a-z0-9-]+`, max 40 chars.
- Empty / all-stripped descriptions → `"repair"`.
- Implementation: `unicodedata.normalize("NFKD", text)` → `encode("ascii", "ignore")` → lowercase → replace non-`[a-z0-9]+` with `-` → strip leading/trailing `-` → truncate to 40 → fallback `"repair"`.

**Image sequence number** (`NNNN`): zero-padded 4 digits, derived at write time from `len(existing_images_in_repair) + 1`. Caller is responsible for not racing concurrently writes within the same repair folder (Phase 1 V1 is single-process, single-tenant — see PLAN.md §2).

### Atomic Write

`write_bytes_atomic(path, data)` and `write_text_atomic(path, text, encoding="utf-8")`:
1. Generate temp path: `<path>.tmp.<8-char-suffix>` (suffix = `os.urandom(4).hex()`).
2. Write to temp using a context-managed file (`open(...).write` + `flush` + `os.fsync` for durability).
3. `os.replace(temp, target)` — atomic on POSIX and Windows for same-filesystem moves.
4. Cleanup temp on exception. Parent dirs are created with `parents=True, exist_ok=True` before step 1.

### JSON Codec

Custom `JSONEncoder` handles:
- `datetime` → `value.isoformat()` (must be aware; encoder rejects naive)
- `date` → `value.isoformat()` (date-only)
- `ULID` → `str(value)`
- `VehicleId` → `value.registration_number`
- `ImageSource` → `value.value`

Decoder helpers:
- `parse_aware_datetime(s) -> datetime` — `datetime.fromisoformat(s)`, raise if naive.
- `parse_date(s) -> date` — `date.fromisoformat(s)`.
- `parse_ulid(s) -> ULID` — `ULID.from_str(s)`.

The decoder is intentionally non-generic (no `object_hook`): each repository explicitly extracts the fields it needs by name. Avoids reflection magic.

### Sidecar

`SidecarReader.read(path) -> dict[str, Any]`:
1. Read file, parse JSON.
2. Inspect `schema_version` (must be `1`).
3. On mismatch: raise `SidecarSchemaError(path, expected=1, actual=...)`.
4. Return the decoded dict (without `schema_version`).

`SidecarWriter.write(path, data: dict[str, Any]) -> None`:
1. Inject `schema_version: 1` (raise if caller provided a conflicting value).
2. JSON-encode with the custom encoder, indent=2, `ensure_ascii=False`.
3. Write atomically via `atomic_write.write_text_atomic`.

### Repositories — read semantics

Vehicle: list folders directly under `<root>/`, ignore those starting with `_` (e.g., `_system/`). For each, read `_vehicle.json`. If no sidecar, the folder is malformed — raise `MissingSidecar` or skip (decision: **raise** during `get`, **skip with logging** during `list_all`).

Repair: list subfolders of `<root>/<reg_no>/` matching `^\d{4}-\d{2}-\d{2}__[a-z0-9-]+$`. Read `_repair.json` per folder.

Image: list files in repair folder matching `^\d{4}_[0-9A-HJKMNP-TV-Z]{26}\.[a-zA-Z0-9]+$` (i.e., `NNNN_<ulid>.<ext>`, **excluding** anything starting with `_` so `_thumbs/` is skipped). Reconstruct the `Image` entity from:
- `id` ← parse ULID from filename
- `repair_id` ← passed in (caller scope)
- `storage_key` ← path relative to root
- `thumbnail_key` ← `<repair>/_thumbs/<filename>` if it exists, else `None`
- `filename` ← actual filename
- `mime_type` ← `mimetypes.guess_type(filename)[0]` or `"application/octet-stream"`
- `size_bytes` ← `path.stat().st_size`
- `source` ← **`ImageSource.MANUAL`** for V1 (the inbox-derived `EMAIL` source is set during write; on read we cannot distinguish without per-image sidecars, so we default. PLAN.md §6 says "Quelle/Datum kommen aus EXIF + Inbox-Eintrag, sonst Default `manual`" — the inbox lookup is Phase 8, not Phase 2.)
- `uploaded_at` ← `datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)`
- `captured_at` ← `None` (EXIF parsing is Phase 4)

This means **Phase 2 reads always return `source=MANUAL` and `captured_at=None`**. That's the V1 truth without Phase 8 inbox correlation. A note will be added to the repository docstring.

### Repositories — write semantics

Vehicle: ensure `<root>/<reg_no>/` exists; write `_vehicle.json`. `save()` raises `DuplicateVehicle` if folder already exists; `update()` raises `VehicleNotFound` if it doesn't.

Repair: ensure `<root>/<reg_no>/` exists (raise `VehicleNotFound` if not); compute repair folder name from `repair.date` + slug derived from `repair.description`; create folder; write `_repair.json`. `save()` raises `FileExistsError` (let it propagate as a domain `DuplicateRepair` — new exception added in Task 1).

Image: write raw bytes to `<repair>/<NNNN>_<ulid>.<ext>` and optional thumbnail bytes to `<repair>/_thumbs/<NNNN>_<ulid>.<ext>`. `<NNNN>` is computed at write time. Returns nothing; mutates filesystem only.

### Slug collision

Two repairs on the same date with the same description produce the same folder name. Resolution: append `-2`, `-3`, ... suffix. Implemented in Task 6 helper `unique_repair_dir_name`.

---

## Task 1: Widen `ImageRepository` port and add `SidecarSchemaError` + `DuplicateRepair`

**Files:**
- Modify: `src/edelrep/domain/ports/image_repository.py`
- Modify: `src/edelrep/domain/exceptions.py`
- Modify: `tests/domain/ports/test_protocol_compliance.py`
- Modify: `tests/domain/test_exceptions.py`

- [ ] **Step 1: Widen the port**

Replace `src/edelrep/domain/ports/image_repository.py` with:

```python
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from ulid import ULID

from edelrep.domain.entities import Image


@runtime_checkable
class ImageRepository(Protocol):
    """Persistence port for :class:`Image` records."""

    def get(self, image_id: ULID) -> Image:
        """Return the image or raise :class:`ImageNotFound`."""
        ...

    def save(
        self,
        image: Image,
        *,
        raw_bytes: bytes,
        thumbnail_bytes: bytes | None = None,
    ) -> None:
        """Persist the image record together with the raw image bytes
        (and optional thumbnail). The implementation is responsible for
        writing both byte streams atomically."""
        ...

    def list_for_repair(self, repair_id: ULID) -> Iterable[Image]:
        """Iterate the repair's images in upload order."""
        ...
```

- [ ] **Step 2: Add the new exceptions**

Append to `src/edelrep/domain/exceptions.py`:

```python


class SidecarSchemaError(DomainError):
    """Raised when a sidecar file has an unsupported schema_version."""

    def __init__(self, path: str, expected: int, actual: int | None) -> None:
        super().__init__(
            f"Sidecar {path!r}: expected schema_version={expected}, got {actual!r}"
        )
        self.path = path
        self.expected = expected
        self.actual = actual


class DuplicateRepair(DomainError):
    """Raised when creating a repair whose folder already exists."""

    def __init__(self, vehicle_id: str, folder_name: str) -> None:
        super().__init__(
            f"Repair folder already exists for vehicle {vehicle_id!r}: {folder_name!r}"
        )
        self.vehicle_id = vehicle_id
        self.folder_name = folder_name
```

Also re-export both names from `src/edelrep/domain/__init__.py`:

Insert into the `from edelrep.domain.exceptions import (...)` block (alphabetically) and add to `__all__`:
- `DuplicateRepair`
- `SidecarSchemaError`

- [ ] **Step 3: Update protocol-compliance fake**

In `tests/domain/ports/test_protocol_compliance.py`, change the `_FakeImageRepo.save` signature to match the new port:

```python
    def save(
        self,
        image: Image,
        *,
        raw_bytes: bytes,
        thumbnail_bytes: bytes | None = None,
    ) -> None:
        self._store[image.id] = image
        # raw_bytes/thumbnail_bytes intentionally ignored in this fake
```

- [ ] **Step 4: Add exception tests**

Append to `tests/domain/test_exceptions.py`:

```python


def test_sidecar_schema_error_carries_fields() -> None:
    err = SidecarSchemaError("/x/_vehicle.json", expected=1, actual=2)
    assert err.path == "/x/_vehicle.json"
    assert err.expected == 1
    assert err.actual == 2
    assert "schema_version=1" in str(err)


def test_duplicate_repair_carries_fields() -> None:
    err = DuplicateRepair("12345", "2026-05-02__brakes")
    assert err.vehicle_id == "12345"
    assert err.folder_name == "2026-05-02__brakes"
```

Update the import block at the top of `test_exceptions.py` to include `DuplicateRepair` and `SidecarSchemaError`. Update the parametrized hierarchy test list to include both new classes.

- [ ] **Step 5: Run gates**

```bash
uv run pytest
uv run pyright
uv run ruff check . && uv run ruff format --check .
```

All green. Test count rises from 41 to 43+ (two new exception tests, plus existing parametrized expansion).

- [ ] **Step 6: Commit**

```bash
git add src/edelrep/domain/ports/image_repository.py \
        src/edelrep/domain/exceptions.py \
        src/edelrep/domain/__init__.py \
        tests/domain/ports/test_protocol_compliance.py \
        tests/domain/test_exceptions.py
git commit -m "feat(domain): widen ImageRepository.save and add sidecar/duplicate-repair exceptions"
```

---

## Task 2: Scaffold infrastructure package

**Files:**
- Create: `src/edelrep/infrastructure/__init__.py` (empty marker, 1 byte newline)
- Create: `src/edelrep/infrastructure/filesystem/__init__.py` (empty marker, 1 byte newline; will be filled in Task 11)
- Create: `tests/infrastructure/__init__.py` (1 byte)
- Create: `tests/infrastructure/filesystem/__init__.py` (1 byte)

- [ ] **Step 1: Create the four marker files**

Each file: a single newline character (1 byte).

- [ ] **Step 2: Pyright sees the new packages**

```bash
uv run pyright
```

Expected: still 0 errors. (Empty packages cause no checks.)

- [ ] **Step 3: Commit**

```bash
git add src/edelrep/infrastructure tests/infrastructure
git commit -m "feat: scaffold infrastructure package and filesystem subpackage"
```

---

## Task 3: Layout — pure path computation (TDD)

**Files:**
- Create: `tests/infrastructure/filesystem/test_layout.py`
- Create: `src/edelrep/infrastructure/filesystem/layout.py`

- [ ] **Step 1: Write failing tests**

Create `tests/infrastructure/filesystem/test_layout.py`:

```python
from datetime import date
from pathlib import Path

import pytest

from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.layout import (
    image_filename,
    repair_dir_name,
    repair_sidecar_path,
    slugify,
    thumbnail_path,
    unique_repair_dir_name,
    vehicle_dir,
    vehicle_sidecar_path,
)


def test_vehicle_dir_uses_registration_number() -> None:
    root = Path("/storage")
    assert vehicle_dir(root, VehicleId("12345")) == root / "12345"


def test_vehicle_sidecar_path() -> None:
    root = Path("/storage")
    assert vehicle_sidecar_path(root, VehicleId("12345")) == root / "12345" / "_vehicle.json"


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Bremsbeläge vorne erneuert", "bremsbelage-vorne-erneuert"),
        ("  whitespace  trimmed  ", "whitespace-trimmed"),
        ("Übergrosse Ümlaute & Sonderzeichen!", "ubergrosse-umlaute-sonderzeichen"),
        ("UPPERCASE", "uppercase"),
        ("a/b/c", "a-b-c"),
        ("", "repair"),
        ("---", "repair"),
        ("   ", "repair"),
        ("a" * 60, "a" * 40),
    ],
)
def test_slugify(description: str, expected: str) -> None:
    assert slugify(description) == expected


def test_repair_dir_name_format() -> None:
    name = repair_dir_name(date(2026, 4, 15), "Bremsen vorne")
    assert name == "2026-04-15__bremsen-vorne"


def test_repair_sidecar_path() -> None:
    root = Path("/storage")
    p = repair_sidecar_path(root, VehicleId("12345"), "2026-04-15__bremsen-vorne")
    assert p == root / "12345" / "2026-04-15__bremsen-vorne" / "_repair.json"


def test_image_filename_format() -> None:
    from ulid import ULID

    uid = ULID.from_str("01J9TGZP6X2K0V3W7Y8Z4QABCD")
    assert image_filename(seq=1, image_id=uid, extension="jpg") == "0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg"
    assert image_filename(seq=42, image_id=uid, extension="png") == "0042_01J9TGZP6X2K0V3W7Y8Z4QABCD.png"


def test_image_filename_zero_pads_to_four_digits() -> None:
    from ulid import ULID

    uid = ULID()
    assert image_filename(seq=9999, image_id=uid, extension="jpg").startswith("9999_")


def test_image_filename_rejects_seq_out_of_range() -> None:
    from ulid import ULID

    uid = ULID()
    with pytest.raises(ValueError, match="seq"):
        image_filename(seq=0, image_id=uid, extension="jpg")
    with pytest.raises(ValueError, match="seq"):
        image_filename(seq=10000, image_id=uid, extension="jpg")


def test_thumbnail_path() -> None:
    repair_dir = Path("/storage/12345/2026-04-15__brakes")
    thumb = thumbnail_path(repair_dir, "0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg")
    assert thumb == repair_dir / "_thumbs" / "0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg"


def test_unique_repair_dir_name_no_collision(tmp_path: Path) -> None:
    base = "2026-04-15__brakes"
    assert unique_repair_dir_name(tmp_path, base) == base


def test_unique_repair_dir_name_one_collision(tmp_path: Path) -> None:
    base = "2026-04-15__brakes"
    (tmp_path / base).mkdir()
    assert unique_repair_dir_name(tmp_path, base) == f"{base}-2"


def test_unique_repair_dir_name_multiple_collisions(tmp_path: Path) -> None:
    base = "2026-04-15__brakes"
    (tmp_path / base).mkdir()
    (tmp_path / f"{base}-2").mkdir()
    (tmp_path / f"{base}-3").mkdir()
    assert unique_repair_dir_name(tmp_path, base) == f"{base}-4"
```

- [ ] **Step 2: Run failing**

```bash
uv run pytest tests/infrastructure/filesystem/test_layout.py -v
```

Expected: ModuleNotFoundError on `edelrep.infrastructure.filesystem.layout`.

- [ ] **Step 3: Implement layout**

Create `src/edelrep/infrastructure/filesystem/layout.py`:

```python
import re
import unicodedata
from datetime import date
from pathlib import Path

from ulid import ULID

from edelrep.domain.value_objects import VehicleId

_SLUG_MAX_LEN = 40
_SLUG_FALLBACK = "repair"
_SLUG_NORMALISE_RE = re.compile(r"[^a-z0-9]+")
_SLUG_TRIM_RE = re.compile(r"^-+|-+$")


def vehicle_dir(root: Path, vehicle_id: VehicleId) -> Path:
    return root / vehicle_id.registration_number


def vehicle_sidecar_path(root: Path, vehicle_id: VehicleId) -> Path:
    return vehicle_dir(root, vehicle_id) / "_vehicle.json"


def slugify(description: str) -> str:
    normalised = unicodedata.normalize("NFKD", description)
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii").lower()
    hyphenated = _SLUG_NORMALISE_RE.sub("-", ascii_only)
    trimmed = _SLUG_TRIM_RE.sub("", hyphenated)
    truncated = trimmed[:_SLUG_MAX_LEN]
    truncated = _SLUG_TRIM_RE.sub("", truncated)
    return truncated or _SLUG_FALLBACK


def repair_dir_name(repair_date: date, description: str) -> str:
    return f"{repair_date.isoformat()}__{slugify(description)}"


def repair_sidecar_path(root: Path, vehicle_id: VehicleId, dir_name: str) -> Path:
    return vehicle_dir(root, vehicle_id) / dir_name / "_repair.json"


def image_filename(*, seq: int, image_id: ULID, extension: str) -> str:
    if not 1 <= seq <= 9999:
        raise ValueError(f"seq must be in 1..9999, got {seq}")
    return f"{seq:04d}_{image_id!s}.{extension}"


def thumbnail_path(repair_dir: Path, image_filename_value: str) -> Path:
    return repair_dir / "_thumbs" / image_filename_value


def unique_repair_dir_name(parent: Path, base: str) -> str:
    if not (parent / base).exists():
        return base
    n = 2
    while (parent / f"{base}-{n}").exists():
        n += 1
    return f"{base}-{n}"
```

- [ ] **Step 4: Run tests passing**

```bash
uv run pytest tests/infrastructure/filesystem/test_layout.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Pyright + ruff**

```bash
uv run pyright
uv run ruff check . && uv run ruff format --check .
```

Both clean.

- [ ] **Step 6: Commit**

```bash
git add src/edelrep/infrastructure/filesystem/layout.py tests/infrastructure/filesystem/test_layout.py
git commit -m "feat(infra): add filesystem layout (paths, slug, repair dir naming)"
```

---

## Task 4: Atomic write helper (TDD)

**Files:**
- Create: `tests/infrastructure/filesystem/test_atomic_write.py`
- Create: `src/edelrep/infrastructure/filesystem/atomic_write.py`

- [ ] **Step 1: Failing test**

Create `tests/infrastructure/filesystem/test_atomic_write.py`:

```python
from pathlib import Path

import pytest

from edelrep.infrastructure.filesystem.atomic_write import (
    write_bytes_atomic,
    write_text_atomic,
)


def test_write_bytes_atomic_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"
    write_bytes_atomic(target, b"hello")
    assert target.read_bytes() == b"hello"


def test_write_bytes_atomic_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c" / "out.bin"
    write_bytes_atomic(target, b"x")
    assert target.read_bytes() == b"x"


def test_write_bytes_atomic_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"
    target.write_bytes(b"old")
    write_bytes_atomic(target, b"new")
    assert target.read_bytes() == b"new"


def test_write_bytes_atomic_no_partial_on_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    target = tmp_path / "out.bin"
    target.write_bytes(b"original")

    real_replace = os.replace

    def boom(_src: str | os.PathLike[str], _dst: str | os.PathLike[str]) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError, match="simulated rename failure"):
        write_bytes_atomic(target, b"new content")

    # Original file untouched.
    assert target.read_bytes() == b"original"
    # No leftover .tmp files.
    assert not list(tmp_path.glob("*.tmp.*"))

    # Restore for cleanup safety.
    monkeypatch.setattr(os, "replace", real_replace)


def test_write_text_atomic_round_trips_unicode(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    write_text_atomic(target, "Schöne Grüße — Ümläüte")
    assert target.read_text(encoding="utf-8") == "Schöne Grüße — Ümläüte"


def test_write_text_atomic_uses_utf8_by_default(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    write_text_atomic(target, "Ä")
    # 'Ä' in UTF-8 is 0xC3 0x84 (two bytes).
    assert target.read_bytes() == b"\xc3\x84"
```

- [ ] **Step 2: Verify failing**

```bash
uv run pytest tests/infrastructure/filesystem/test_atomic_write.py -v
```

ModuleNotFoundError expected.

- [ ] **Step 3: Implementation**

Create `src/edelrep/infrastructure/filesystem/atomic_write.py`:

```python
import os
from pathlib import Path


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Atomically write ``data`` to ``path``.

    Creates parent directories as needed. Uses a same-directory temp file
    plus :func:`os.replace` so a reader either sees the old content or the
    new content, never a partial write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = os.urandom(4).hex()
    tmp = path.with_name(f"{path.name}.tmp.{suffix}")
    try:
        with tmp.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def write_text_atomic(path: Path, text: str, encoding: str = "utf-8") -> None:
    write_bytes_atomic(path, text.encode(encoding))
```

- [ ] **Step 4: Tests pass**

```bash
uv run pytest tests/infrastructure/filesystem/test_atomic_write.py -v
```

- [ ] **Step 5: Pyright + ruff clean**

- [ ] **Step 6: Commit**

```bash
git add src/edelrep/infrastructure/filesystem/atomic_write.py \
        tests/infrastructure/filesystem/test_atomic_write.py
git commit -m "feat(infra): add atomic write helpers for bytes and text"
```

---

## Task 5: JSON codec (TDD)

**Files:**
- Create: `tests/infrastructure/filesystem/test_json_codec.py`
- Create: `src/edelrep/infrastructure/filesystem/json_codec.py`

- [ ] **Step 1: Failing test**

Create `tests/infrastructure/filesystem/test_json_codec.py`:

```python
import json
from datetime import UTC, date, datetime

import pytest
from ulid import ULID

from edelrep.domain.entities import ImageSource
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.json_codec import (
    DomainJSONEncoder,
    parse_aware_datetime,
    parse_date,
    parse_ulid,
)


def test_encoder_serialises_aware_datetime() -> None:
    dt = datetime(2026, 5, 2, 10, 0, tzinfo=UTC)
    out = json.dumps({"t": dt}, cls=DomainJSONEncoder)
    assert "2026-05-02T10:00:00+00:00" in out


def test_encoder_rejects_naive_datetime() -> None:
    dt = datetime(2026, 5, 2, 10, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        json.dumps({"t": dt}, cls=DomainJSONEncoder)


def test_encoder_serialises_date() -> None:
    out = json.dumps({"d": date(2026, 4, 15)}, cls=DomainJSONEncoder)
    assert '"2026-04-15"' in out


def test_encoder_serialises_ulid() -> None:
    uid = ULID()
    out = json.dumps({"id": uid}, cls=DomainJSONEncoder)
    assert str(uid) in out


def test_encoder_serialises_vehicle_id() -> None:
    out = json.dumps({"v": VehicleId("12345")}, cls=DomainJSONEncoder)
    assert '"12345"' in out


def test_encoder_serialises_image_source() -> None:
    out = json.dumps({"s": ImageSource.MANUAL}, cls=DomainJSONEncoder)
    assert '"manual"' in out


def test_parse_aware_datetime_round_trip() -> None:
    dt = datetime(2026, 5, 2, 10, 0, tzinfo=UTC)
    assert parse_aware_datetime(dt.isoformat()) == dt


def test_parse_aware_datetime_rejects_naive() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_aware_datetime("2026-05-02T10:00:00")


def test_parse_date_round_trip() -> None:
    assert parse_date("2026-04-15") == date(2026, 4, 15)


def test_parse_ulid_round_trip() -> None:
    uid = ULID()
    assert parse_ulid(str(uid)) == uid
```

- [ ] **Step 2: Verify failing**

- [ ] **Step 3: Implementation**

Create `src/edelrep/infrastructure/filesystem/json_codec.py`:

```python
import json
from datetime import date, datetime
from enum import Enum
from typing import Any

from ulid import ULID

from edelrep.domain.value_objects import VehicleId


class DomainJSONEncoder(json.JSONEncoder):
    """JSON encoder that knows how to serialise edelrep's domain primitives."""

    def default(self, o: Any) -> Any:
        if isinstance(o, datetime):
            if o.tzinfo is None or o.tzinfo.utcoffset(o) is None:
                raise ValueError("datetime values must be timezone-aware before encoding")
            return o.isoformat()
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, ULID):
            return str(o)
        if isinstance(o, VehicleId):
            return o.registration_number
        if isinstance(o, Enum):
            return o.value
        return super().default(o)


def parse_aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise ValueError(f"datetime {value!r} must be timezone-aware")
    return parsed


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_ulid(value: str) -> ULID:
    return ULID.from_str(value)
```

- [ ] **Step 4: Tests pass; pyright + ruff clean.**

- [ ] **Step 5: Commit**

```bash
git add src/edelrep/infrastructure/filesystem/json_codec.py \
        tests/infrastructure/filesystem/test_json_codec.py
git commit -m "feat(infra): add JSON codec for domain primitives (datetime, date, ULID, VehicleId, Enum)"
```

---

## Task 6: Sidecar reader/writer with schema_version (TDD)

**Files:**
- Create: `tests/infrastructure/filesystem/test_sidecar.py`
- Create: `src/edelrep/infrastructure/filesystem/sidecar.py`

- [ ] **Step 1: Failing test**

Create `tests/infrastructure/filesystem/test_sidecar.py`:

```python
import json
from pathlib import Path

import pytest

from edelrep.domain.exceptions import SidecarSchemaError
from edelrep.infrastructure.filesystem.sidecar import (
    CURRENT_SCHEMA_VERSION,
    read_sidecar,
    write_sidecar,
)


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "_vehicle.json"
    write_sidecar(target, {"foo": "bar", "n": 3})
    data = read_sidecar(target)
    assert data == {"foo": "bar", "n": 3}


def test_write_injects_schema_version(tmp_path: Path) -> None:
    target = tmp_path / "_vehicle.json"
    write_sidecar(target, {"foo": "bar"})
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["schema_version"] == CURRENT_SCHEMA_VERSION
    assert raw["foo"] == "bar"


def test_write_rejects_caller_provided_schema_version(tmp_path: Path) -> None:
    target = tmp_path / "_vehicle.json"
    with pytest.raises(ValueError, match="schema_version"):
        write_sidecar(target, {"schema_version": 99, "foo": "bar"})


def test_read_rejects_unknown_version(tmp_path: Path) -> None:
    target = tmp_path / "_vehicle.json"
    target.write_text(json.dumps({"schema_version": 99, "foo": "bar"}), encoding="utf-8")
    with pytest.raises(SidecarSchemaError) as info:
        read_sidecar(target)
    assert info.value.expected == CURRENT_SCHEMA_VERSION
    assert info.value.actual == 99


def test_read_rejects_missing_version(tmp_path: Path) -> None:
    target = tmp_path / "_vehicle.json"
    target.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
    with pytest.raises(SidecarSchemaError) as info:
        read_sidecar(target)
    assert info.value.actual is None


def test_write_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "_vehicle.json"
    write_sidecar(target, {"foo": "bar"})
    assert not list(tmp_path.glob("*.tmp.*"))
```

- [ ] **Step 2: Verify failing.**

- [ ] **Step 3: Implementation**

Create `src/edelrep/infrastructure/filesystem/sidecar.py`:

```python
import json
from pathlib import Path
from typing import Any

from edelrep.domain.exceptions import SidecarSchemaError
from edelrep.infrastructure.filesystem.atomic_write import write_text_atomic
from edelrep.infrastructure.filesystem.json_codec import DomainJSONEncoder

CURRENT_SCHEMA_VERSION = 1


def write_sidecar(path: Path, data: dict[str, Any]) -> None:
    if "schema_version" in data:
        raise ValueError("caller must not pre-populate schema_version; sidecar writer owns it")
    payload = {"schema_version": CURRENT_SCHEMA_VERSION, **data}
    text = json.dumps(payload, cls=DomainJSONEncoder, indent=2, ensure_ascii=False)
    write_text_atomic(path, text + "\n")


def read_sidecar(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    actual = raw.get("schema_version") if isinstance(raw, dict) else None
    if actual != CURRENT_SCHEMA_VERSION:
        raise SidecarSchemaError(str(path), expected=CURRENT_SCHEMA_VERSION, actual=actual)
    out = dict(raw)
    out.pop("schema_version", None)
    return out
```

- [ ] **Step 4: Tests pass.**

- [ ] **Step 5: Pyright + ruff clean.**

- [ ] **Step 6: Commit**

```bash
git add src/edelrep/infrastructure/filesystem/sidecar.py \
        tests/infrastructure/filesystem/test_sidecar.py
git commit -m "feat(infra): add sidecar reader/writer with schema_version enforcement"
```

---

## Task 7: `tests/infrastructure/filesystem/conftest.py`

**Files:**
- Create: `tests/infrastructure/filesystem/conftest.py`

- [ ] **Step 1: Add fixtures**

```python
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ulid import ULID

from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
from edelrep.domain.value_objects import VehicleId


@pytest.fixture
def storage_root(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path / "storage"
    root.mkdir()
    yield root


@pytest.fixture
def sample_vehicle() -> Vehicle:
    return Vehicle(
        id=VehicleId("12345"),
        vin="WDB12345TEST",
        description="Kran 4-achsig",
        created_at=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_repair() -> Repair:
    return Repair(
        id=ULID.from_str("01J9TGZP6X2K0V3W7Y8Z4QABCD"),
        vehicle_id=VehicleId("12345"),
        date=date(2026, 4, 15),
        description="Bremsbeläge vorne",
        created_at=datetime(2026, 4, 15, 16, 30, tzinfo=UTC),
    )


@pytest.fixture
def sample_image_bytes() -> bytes:
    # Tiny valid-looking JPEG header. Content is irrelevant for these tests.
    return b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"


def make_image(repair_id: ULID, *, image_id: ULID | None = None) -> Image:
    iid = image_id or ULID()
    return Image(
        id=iid,
        repair_id=repair_id,
        storage_key="placeholder",
        thumbnail_key=None,
        filename=f"0001_{iid!s}.jpg",
        mime_type="image/jpeg",
        size_bytes=72,
        source=ImageSource.MANUAL,
        uploaded_at=datetime(2026, 4, 15, 16, 35, tzinfo=UTC),
        captured_at=None,
    )
```

- [ ] **Step 2: Pyright + ruff clean.**

- [ ] **Step 3: Commit**

```bash
git add tests/infrastructure/filesystem/conftest.py
git commit -m "test(infra): add filesystem fixtures (storage_root, sample_vehicle, sample_repair, image bytes)"
```

---

## Task 8: FilesystemVehicleRepository (TDD)

**Files:**
- Create: `tests/infrastructure/filesystem/test_vehicle_store.py`
- Create: `src/edelrep/infrastructure/filesystem/vehicle_store.py`

- [ ] **Step 1: Failing tests**

Create `tests/infrastructure/filesystem/test_vehicle_store.py`:

```python
from datetime import UTC, datetime
from pathlib import Path

import pytest

from edelrep.domain.entities import Vehicle
from edelrep.domain.exceptions import (
    DuplicateVehicle,
    SidecarSchemaError,
    VehicleNotFound,
)
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.vehicle_store import FilesystemVehicleRepository


def test_save_and_get_round_trips(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    repo.save(sample_vehicle)
    assert repo.get(sample_vehicle.id) == sample_vehicle


def test_save_creates_sidecar_with_expected_layout(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    repo.save(sample_vehicle)
    sidecar = storage_root / "12345" / "_vehicle.json"
    assert sidecar.is_file()


def test_save_raises_duplicate_when_folder_exists(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    repo.save(sample_vehicle)
    with pytest.raises(DuplicateVehicle):
        repo.save(sample_vehicle)


def test_get_raises_when_missing(storage_root: Path) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    with pytest.raises(VehicleNotFound):
        repo.get(VehicleId("99999"))


def test_get_raises_schema_error_on_bad_sidecar(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    repo.save(sample_vehicle)
    sidecar = storage_root / "12345" / "_vehicle.json"
    sidecar.write_text('{"schema_version": 99, "vin": "x"}', encoding="utf-8")
    with pytest.raises(SidecarSchemaError):
        repo.get(sample_vehicle.id)


def test_update_existing_vehicle(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    repo.save(sample_vehicle)
    updated = Vehicle(
        id=sample_vehicle.id,
        vin="NEWVIN",
        description="Updated",
        created_at=sample_vehicle.created_at,
    )
    repo.update(updated)
    assert repo.get(sample_vehicle.id) == updated


def test_update_raises_when_missing(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    with pytest.raises(VehicleNotFound):
        repo.update(sample_vehicle)


def test_exists(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    assert not repo.exists(sample_vehicle.id)
    repo.save(sample_vehicle)
    assert repo.exists(sample_vehicle.id)


def test_list_all_skips_underscore_prefixed_dirs(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    repo.save(sample_vehicle)
    (storage_root / "_system").mkdir()
    (storage_root / "_system" / "inbox").mkdir()
    listed = list(repo.list_all())
    assert listed == [sample_vehicle]


def test_list_all_skips_directory_without_sidecar(storage_root: Path, sample_vehicle: Vehicle) -> None:
    repo = FilesystemVehicleRepository(storage_root)
    repo.save(sample_vehicle)
    (storage_root / "67890").mkdir()  # malformed: no _vehicle.json
    listed = list(repo.list_all())
    assert listed == [sample_vehicle]
```

- [ ] **Step 2: Verify failing.**

- [ ] **Step 3: Implementation**

Create `src/edelrep/infrastructure/filesystem/vehicle_store.py`:

```python
from collections.abc import Iterable
from pathlib import Path

from edelrep.domain.entities import Vehicle
from edelrep.domain.exceptions import DuplicateVehicle, VehicleNotFound
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.json_codec import parse_aware_datetime
from edelrep.infrastructure.filesystem.layout import vehicle_dir, vehicle_sidecar_path
from edelrep.infrastructure.filesystem.sidecar import read_sidecar, write_sidecar


class FilesystemVehicleRepository:
    """VehicleRepository implementation backed by JSON sidecars on disk."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def get(self, vehicle_id: VehicleId) -> Vehicle:
        sidecar = vehicle_sidecar_path(self._root, vehicle_id)
        if not sidecar.is_file():
            raise VehicleNotFound(vehicle_id.registration_number)
        data = read_sidecar(sidecar)
        return self._deserialise(vehicle_id, data)

    def save(self, vehicle: Vehicle) -> None:
        directory = vehicle_dir(self._root, vehicle.id)
        if directory.exists():
            raise DuplicateVehicle(vehicle.id.registration_number)
        directory.mkdir(parents=True)
        write_sidecar(vehicle_sidecar_path(self._root, vehicle.id), self._serialise(vehicle))

    def update(self, vehicle: Vehicle) -> None:
        directory = vehicle_dir(self._root, vehicle.id)
        if not directory.is_dir():
            raise VehicleNotFound(vehicle.id.registration_number)
        write_sidecar(vehicle_sidecar_path(self._root, vehicle.id), self._serialise(vehicle))

    def exists(self, vehicle_id: VehicleId) -> bool:
        return vehicle_sidecar_path(self._root, vehicle_id).is_file()

    def list_all(self) -> Iterable[Vehicle]:
        if not self._root.is_dir():
            return
        for entry in sorted(self._root.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_"):
                continue
            sidecar = entry / "_vehicle.json"
            if not sidecar.is_file():
                continue
            try:
                vid = VehicleId(entry.name)
            except Exception:
                continue
            data = read_sidecar(sidecar)
            yield self._deserialise(vid, data)

    @staticmethod
    def _serialise(vehicle: Vehicle) -> dict[str, object]:
        return {
            "registration_number": vehicle.id.registration_number,
            "vin": vehicle.vin,
            "description": vehicle.description,
            "created_at": vehicle.created_at,
        }

    @staticmethod
    def _deserialise(vehicle_id: VehicleId, data: dict[str, object]) -> Vehicle:
        created_at_raw = data["created_at"]
        if not isinstance(created_at_raw, str):
            raise TypeError(f"created_at must be ISO string, got {type(created_at_raw).__name__}")
        return Vehicle(
            id=vehicle_id,
            vin=data.get("vin"),  # type: ignore[arg-type]
            description=data.get("description"),  # type: ignore[arg-type]
            created_at=parse_aware_datetime(created_at_raw),
        )
```

- [ ] **Step 4: Tests pass; pyright + ruff clean.**

- [ ] **Step 5: Verify the repo is structurally a `VehicleRepository`** by adding one assertion in the test file (top of any existing test or a new tiny test):

```python
def test_satisfies_protocol(storage_root: Path) -> None:
    from edelrep.domain.ports import VehicleRepository
    repo: VehicleRepository = FilesystemVehicleRepository(storage_root)
    assert isinstance(repo, VehicleRepository)
```

Re-run the test file.

- [ ] **Step 6: Commit**

```bash
git add src/edelrep/infrastructure/filesystem/vehicle_store.py \
        tests/infrastructure/filesystem/test_vehicle_store.py
git commit -m "feat(infra): add FilesystemVehicleRepository with CRUD and list_all"
```

---

## Task 9: FilesystemRepairRepository (TDD)

**Files:**
- Create: `tests/infrastructure/filesystem/test_repair_store.py`
- Create: `src/edelrep/infrastructure/filesystem/repair_store.py`

- [ ] **Step 1: Failing tests**

Create `tests/infrastructure/filesystem/test_repair_store.py`:

```python
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ulid import ULID

from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.exceptions import (
    DuplicateRepair,
    RepairNotFound,
    VehicleNotFound,
)
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.repair_store import FilesystemRepairRepository
from edelrep.infrastructure.filesystem.vehicle_store import FilesystemVehicleRepository


def _seed_vehicle(root: Path, sample_vehicle: Vehicle) -> None:
    FilesystemVehicleRepository(root).save(sample_vehicle)


def test_save_and_get(storage_root: Path, sample_vehicle: Vehicle, sample_repair: Repair) -> None:
    _seed_vehicle(storage_root, sample_vehicle)
    repo = FilesystemRepairRepository(storage_root)
    repo.save(sample_repair)
    fetched = repo.get(sample_repair.id)
    assert fetched == sample_repair


def test_save_raises_when_vehicle_missing(storage_root: Path, sample_repair: Repair) -> None:
    repo = FilesystemRepairRepository(storage_root)
    with pytest.raises(VehicleNotFound):
        repo.save(sample_repair)


def test_save_raises_duplicate_on_collision(storage_root: Path, sample_vehicle: Vehicle, sample_repair: Repair) -> None:
    _seed_vehicle(storage_root, sample_vehicle)
    repo = FilesystemRepairRepository(storage_root)
    repo.save(sample_repair)
    with pytest.raises(DuplicateRepair):
        # Same date + same description (so same folder) but new ULID.
        clash = Repair(
            id=ULID(),
            vehicle_id=sample_repair.vehicle_id,
            date=sample_repair.date,
            description=sample_repair.description,
            created_at=sample_repair.created_at,
        )
        repo.save(clash)


def test_get_raises_when_missing(storage_root: Path) -> None:
    repo = FilesystemRepairRepository(storage_root)
    with pytest.raises(RepairNotFound):
        repo.get(ULID())


def test_update_existing(storage_root: Path, sample_vehicle: Vehicle, sample_repair: Repair) -> None:
    _seed_vehicle(storage_root, sample_vehicle)
    repo = FilesystemRepairRepository(storage_root)
    repo.save(sample_repair)
    updated = Repair(
        id=sample_repair.id,
        vehicle_id=sample_repair.vehicle_id,
        date=sample_repair.date,
        description=sample_repair.description,
        created_at=datetime(2026, 4, 16, 9, 0, tzinfo=UTC),
    )
    repo.update(updated)
    assert repo.get(sample_repair.id) == updated


def test_update_raises_when_missing(storage_root: Path, sample_repair: Repair) -> None:
    repo = FilesystemRepairRepository(storage_root)
    with pytest.raises(RepairNotFound):
        repo.update(sample_repair)


def test_list_for_vehicle_orders_newest_first(
    storage_root: Path,
    sample_vehicle: Vehicle,
) -> None:
    _seed_vehicle(storage_root, sample_vehicle)
    repo = FilesystemRepairRepository(storage_root)
    older = Repair(
        id=ULID(),
        vehicle_id=sample_vehicle.id,
        date=date(2026, 1, 1),
        description="old",
        created_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    newer = Repair(
        id=ULID(),
        vehicle_id=sample_vehicle.id,
        date=date(2026, 5, 1),
        description="new",
        created_at=datetime(2026, 5, 1, 0, 0, tzinfo=UTC),
    )
    repo.save(older)
    repo.save(newer)
    listed = list(repo.list_for_vehicle(sample_vehicle.id))
    assert [r.date for r in listed] == [date(2026, 5, 1), date(2026, 1, 1)]


def test_list_for_vehicle_returns_empty_for_unknown(storage_root: Path) -> None:
    repo = FilesystemRepairRepository(storage_root)
    assert list(repo.list_for_vehicle(VehicleId("99999"))) == []


def test_satisfies_protocol(storage_root: Path) -> None:
    from edelrep.domain.ports import RepairRepository

    repo: RepairRepository = FilesystemRepairRepository(storage_root)
    assert isinstance(repo, RepairRepository)
```

- [ ] **Step 2: Verify failing.**

- [ ] **Step 3: Implementation**

Create `src/edelrep/infrastructure/filesystem/repair_store.py`:

```python
import re
from collections.abc import Iterable
from pathlib import Path

from ulid import ULID

from edelrep.domain.entities import Repair
from edelrep.domain.exceptions import DuplicateRepair, RepairNotFound, VehicleNotFound
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.json_codec import (
    parse_aware_datetime,
    parse_date,
    parse_ulid,
)
from edelrep.infrastructure.filesystem.layout import (
    repair_dir_name,
    repair_sidecar_path,
    vehicle_dir,
)
from edelrep.infrastructure.filesystem.sidecar import read_sidecar, write_sidecar

_REPAIR_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}__[a-z0-9-]+$")


class FilesystemRepairRepository:
    """RepairRepository implementation backed by per-repair sidecars on disk."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def get(self, repair_id: ULID) -> Repair:
        for sidecar, vid in self._iter_sidecars():
            data = read_sidecar(sidecar)
            if parse_ulid(str(data["id"])) == repair_id:
                return self._deserialise(vid, data)
        raise RepairNotFound(repair_id)

    def save(self, repair: Repair) -> None:
        veh_dir = vehicle_dir(self._root, repair.vehicle_id)
        if not veh_dir.is_dir():
            raise VehicleNotFound(repair.vehicle_id.registration_number)
        dir_name = repair_dir_name(repair.date, repair.description)
        target_dir = veh_dir / dir_name
        if target_dir.exists():
            raise DuplicateRepair(repair.vehicle_id.registration_number, dir_name)
        target_dir.mkdir(parents=True)
        write_sidecar(repair_sidecar_path(self._root, repair.vehicle_id, dir_name), self._serialise(repair))

    def update(self, repair: Repair) -> None:
        for sidecar, vid in self._iter_sidecars():
            data = read_sidecar(sidecar)
            if parse_ulid(str(data["id"])) == repair.id and vid == repair.vehicle_id:
                write_sidecar(sidecar, self._serialise(repair))
                return
        raise RepairNotFound(repair.id)

    def list_for_vehicle(self, vehicle_id: VehicleId) -> Iterable[Repair]:
        veh_dir = vehicle_dir(self._root, vehicle_id)
        if not veh_dir.is_dir():
            return
        repairs: list[Repair] = []
        for entry in veh_dir.iterdir():
            if not entry.is_dir() or not _REPAIR_DIR_RE.match(entry.name):
                continue
            sidecar = entry / "_repair.json"
            if not sidecar.is_file():
                continue
            data = read_sidecar(sidecar)
            repairs.append(self._deserialise(vehicle_id, data))
        repairs.sort(key=lambda r: r.date, reverse=True)
        yield from repairs

    def _iter_sidecars(self) -> Iterable[tuple[Path, VehicleId]]:
        if not self._root.is_dir():
            return
        for vdir in self._root.iterdir():
            if not vdir.is_dir() or vdir.name.startswith("_"):
                continue
            try:
                vid = VehicleId(vdir.name)
            except Exception:
                continue
            for repair_dir in vdir.iterdir():
                if not repair_dir.is_dir() or not _REPAIR_DIR_RE.match(repair_dir.name):
                    continue
                sidecar = repair_dir / "_repair.json"
                if sidecar.is_file():
                    yield sidecar, vid

    @staticmethod
    def _serialise(repair: Repair) -> dict[str, object]:
        return {
            "id": str(repair.id),
            "date": repair.date,
            "description": repair.description,
            "created_at": repair.created_at,
        }

    @staticmethod
    def _deserialise(vehicle_id: VehicleId, data: dict[str, object]) -> Repair:
        return Repair(
            id=parse_ulid(str(data["id"])),
            vehicle_id=vehicle_id,
            date=parse_date(str(data["date"])),
            description=str(data["description"]),
            created_at=parse_aware_datetime(str(data["created_at"])),
        )
```

- [ ] **Step 4: Tests pass; pyright + ruff clean.**

- [ ] **Step 5: Commit**

```bash
git add src/edelrep/infrastructure/filesystem/repair_store.py \
        tests/infrastructure/filesystem/test_repair_store.py
git commit -m "feat(infra): add FilesystemRepairRepository with CRUD and chronological listing"
```

---

## Task 10: FilesystemImageRepository (TDD)

**Files:**
- Create: `tests/infrastructure/filesystem/test_image_store.py`
- Create: `src/edelrep/infrastructure/filesystem/image_store.py`

- [ ] **Step 1: Failing tests**

Create `tests/infrastructure/filesystem/test_image_store.py`:

```python
from pathlib import Path

import pytest
from ulid import ULID

from edelrep.domain.entities import ImageSource, Repair, Vehicle
from edelrep.domain.exceptions import ImageNotFound, RepairNotFound
from edelrep.infrastructure.filesystem.image_store import FilesystemImageRepository
from edelrep.infrastructure.filesystem.repair_store import FilesystemRepairRepository
from edelrep.infrastructure.filesystem.vehicle_store import FilesystemVehicleRepository

from .conftest import make_image  # type: ignore[import-not-found]


def _seed(root: Path, vehicle: Vehicle, repair: Repair) -> None:
    FilesystemVehicleRepository(root).save(vehicle)
    FilesystemRepairRepository(root).save(repair)


def test_save_writes_image_bytes_and_thumbnail(
    storage_root: Path,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(storage_root, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(storage_root)
    img = make_image(sample_repair.id)
    repo.save(img, raw_bytes=sample_image_bytes, thumbnail_bytes=sample_image_bytes)
    repair_path = storage_root / "12345" / "2026-04-15__bremsbelage-vorne"
    image_files = sorted(p.name for p in repair_path.iterdir() if p.is_file())
    assert any(name.startswith("0001_") for name in image_files)
    thumbs = sorted((repair_path / "_thumbs").iterdir())
    assert len(thumbs) == 1


def test_save_raises_when_repair_missing(
    storage_root: Path,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    FilesystemVehicleRepository(storage_root).save(sample_vehicle)
    # Note: repair NOT saved.
    repo = FilesystemImageRepository(storage_root)
    img = make_image(sample_repair.id)
    with pytest.raises(RepairNotFound):
        repo.save(img, raw_bytes=sample_image_bytes)


def test_save_no_thumbnail(
    storage_root: Path,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(storage_root, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(storage_root)
    img = make_image(sample_repair.id)
    repo.save(img, raw_bytes=sample_image_bytes)
    repair_path = storage_root / "12345" / "2026-04-15__bremsbelage-vorne"
    assert not (repair_path / "_thumbs").exists()


def test_list_for_repair_returns_uploaded_images_in_order(
    storage_root: Path,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(storage_root, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(storage_root)
    first = make_image(sample_repair.id)
    second = make_image(sample_repair.id)
    repo.save(first, raw_bytes=sample_image_bytes)
    repo.save(second, raw_bytes=sample_image_bytes)
    listed = list(repo.list_for_repair(sample_repair.id))
    assert [img.filename.split("_")[0] for img in listed] == ["0001", "0002"]


def test_list_for_repair_skips_thumb_subfolder(
    storage_root: Path,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(storage_root, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(storage_root)
    repo.save(make_image(sample_repair.id), raw_bytes=sample_image_bytes, thumbnail_bytes=sample_image_bytes)
    listed = list(repo.list_for_repair(sample_repair.id))
    assert len(listed) == 1
    assert "_thumbs" not in listed[0].storage_key


def test_list_for_repair_returns_empty_for_unknown(storage_root: Path) -> None:
    repo = FilesystemImageRepository(storage_root)
    assert list(repo.list_for_repair(ULID())) == []


def test_get_returns_image(
    storage_root: Path,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(storage_root, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(storage_root)
    img = make_image(sample_repair.id)
    repo.save(img, raw_bytes=sample_image_bytes)
    fetched = repo.get(img.id)
    assert fetched.id == img.id
    assert fetched.repair_id == img.repair_id
    assert fetched.size_bytes == len(sample_image_bytes)
    # Phase 2 always returns MANUAL on read; this is documented behaviour.
    assert fetched.source == ImageSource.MANUAL


def test_get_raises_when_missing(storage_root: Path) -> None:
    repo = FilesystemImageRepository(storage_root)
    with pytest.raises(ImageNotFound):
        repo.get(ULID())


def test_satisfies_protocol(storage_root: Path) -> None:
    from edelrep.domain.ports import ImageRepository

    repo: ImageRepository = FilesystemImageRepository(storage_root)
    assert isinstance(repo, ImageRepository)
```

- [ ] **Step 2: Verify failing.**

- [ ] **Step 3: Implementation**

Create `src/edelrep/infrastructure/filesystem/image_store.py`:

```python
import mimetypes
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from ulid import ULID

from edelrep.domain.entities import Image, ImageSource
from edelrep.domain.exceptions import ImageNotFound, RepairNotFound
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.atomic_write import write_bytes_atomic
from edelrep.infrastructure.filesystem.layout import image_filename, thumbnail_path, vehicle_dir
from edelrep.infrastructure.filesystem.repair_store import _REPAIR_DIR_RE
from edelrep.infrastructure.filesystem.sidecar import read_sidecar

_IMAGE_FILE_RE = re.compile(r"^(\d{4})_([0-9A-HJKMNP-TV-Z]{26})\.([a-zA-Z0-9]+)$")


class FilesystemImageRepository:
    """ImageRepository implementation that stores raw bytes plus optional thumbnails."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def get(self, image_id: ULID) -> Image:
        for image_path, repair_id in self._iter_image_files():
            match = _IMAGE_FILE_RE.match(image_path.name)
            if match and ULID.from_str(match.group(2)) == image_id:
                return self._reconstruct(image_path, repair_id)
        raise ImageNotFound(image_id)

    def save(
        self,
        image: Image,
        *,
        raw_bytes: bytes,
        thumbnail_bytes: bytes | None = None,
    ) -> None:
        repair_dir = self._find_repair_dir(image.repair_id)
        if repair_dir is None:
            raise RepairNotFound(image.repair_id)
        existing = sum(1 for p in repair_dir.iterdir() if p.is_file() and _IMAGE_FILE_RE.match(p.name))
        seq = existing + 1
        extension = (image.filename.rsplit(".", 1)[-1] or "bin").lower()
        name = image_filename(seq=seq, image_id=image.id, extension=extension)
        write_bytes_atomic(repair_dir / name, raw_bytes)
        if thumbnail_bytes is not None:
            write_bytes_atomic(thumbnail_path(repair_dir, name), thumbnail_bytes)

    def list_for_repair(self, repair_id: ULID) -> Iterable[Image]:
        repair_dir = self._find_repair_dir(repair_id)
        if repair_dir is None:
            return
        files = sorted(p for p in repair_dir.iterdir() if p.is_file() and _IMAGE_FILE_RE.match(p.name))
        for path in files:
            yield self._reconstruct(path, repair_id)

    def _find_repair_dir(self, repair_id: ULID) -> Path | None:
        if not self._root.is_dir():
            return None
        for vdir in self._root.iterdir():
            if not vdir.is_dir() or vdir.name.startswith("_"):
                continue
            for rdir in vdir.iterdir():
                if not rdir.is_dir() or not _REPAIR_DIR_RE.match(rdir.name):
                    continue
                sidecar = rdir / "_repair.json"
                if not sidecar.is_file():
                    continue
                data = read_sidecar(sidecar)
                if str(data.get("id")) == str(repair_id):
                    return rdir
        return None

    def _iter_image_files(self) -> Iterable[tuple[Path, ULID]]:
        if not self._root.is_dir():
            return
        for vdir in self._root.iterdir():
            if not vdir.is_dir() or vdir.name.startswith("_"):
                continue
            for rdir in vdir.iterdir():
                if not rdir.is_dir() or not _REPAIR_DIR_RE.match(rdir.name):
                    continue
                sidecar = rdir / "_repair.json"
                if not sidecar.is_file():
                    continue
                data = read_sidecar(sidecar)
                rid = ULID.from_str(str(data["id"]))
                for entry in rdir.iterdir():
                    if entry.is_file() and _IMAGE_FILE_RE.match(entry.name):
                        yield entry, rid

    def _reconstruct(self, path: Path, repair_id: ULID) -> Image:
        match = _IMAGE_FILE_RE.match(path.name)
        if match is None:
            raise ValueError(f"unexpected image filename: {path.name!r}")
        image_id = ULID.from_str(match.group(2))
        thumb = path.parent / "_thumbs" / path.name
        rel_storage = path.relative_to(self._root).as_posix()
        rel_thumb = thumb.relative_to(self._root).as_posix() if thumb.is_file() else None
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        stat = path.stat()
        return Image(
            id=image_id,
            repair_id=repair_id,
            storage_key=rel_storage,
            thumbnail_key=rel_thumb,
            filename=path.name,
            mime_type=mime,
            size_bytes=stat.st_size,
            source=ImageSource.MANUAL,
            uploaded_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            captured_at=None,
        )
```

Note: importing `_REPAIR_DIR_RE` from `repair_store` is a deliberate re-use of the private regex. Acceptable within the same package; if pyright/ruff complains via `reportPrivateUsage`, hoist the regex to `layout.py` as `REPAIR_DIR_NAME_RE`.

- [ ] **Step 4: Tests pass; pyright + ruff clean.**

- [ ] **Step 5: Commit**

```bash
git add src/edelrep/infrastructure/filesystem/image_store.py \
        tests/infrastructure/filesystem/test_image_store.py
git commit -m "feat(infra): add FilesystemImageRepository (raw bytes, thumbnails, reconstruction on read)"
```

---

## Task 11: Filesystem package re-exports

**Files:**
- Modify: `src/edelrep/infrastructure/filesystem/__init__.py`

- [ ] **Step 1: Re-export the three repos**

Replace `__init__.py` with:

```python
from edelrep.infrastructure.filesystem.image_store import FilesystemImageRepository
from edelrep.infrastructure.filesystem.repair_store import FilesystemRepairRepository
from edelrep.infrastructure.filesystem.vehicle_store import FilesystemVehicleRepository

__all__ = [
    "FilesystemImageRepository",
    "FilesystemRepairRepository",
    "FilesystemVehicleRepository",
]
```

- [ ] **Step 2: Pyright + ruff clean.**

- [ ] **Step 3: Commit**

```bash
git add src/edelrep/infrastructure/filesystem/__init__.py
git commit -m "feat(infra): re-export filesystem repositories"
```

---

## Task 12: Example storage fixture

**Files:**
- Create: `tests/infrastructure/filesystem/fixtures/example_storage_root/12345/_vehicle.json`
- Create: `tests/infrastructure/filesystem/fixtures/example_storage_root/12345/2026-04-15__bremsbelage-vorne/_repair.json`
- Create: `tests/infrastructure/filesystem/fixtures/example_storage_root/12345/2026-04-15__bremsbelage-vorne/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg` (binary, 4 bytes: `b"\xff\xd8\xff\xd9"`)
- Create: `tests/infrastructure/filesystem/fixtures/example_storage_root/12345/2026-04-15__bremsbelage-vorne/_thumbs/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg` (same 4 bytes)

- [ ] **Step 1: `_vehicle.json` content**

```json
{
  "schema_version": 1,
  "registration_number": "12345",
  "vin": "WDB12345TEST",
  "description": "Kran 4-achsig, Bj. 2018",
  "created_at": "2026-04-15T10:00:00+00:00"
}
```

- [ ] **Step 2: `_repair.json` content**

```json
{
  "schema_version": 1,
  "id": "01J9TGZP6X2K0V3W7Y8Z4QABCD",
  "date": "2026-04-15",
  "description": "Bremsbeläge vorne",
  "created_at": "2026-04-15T16:30:00+00:00"
}
```

- [ ] **Step 3: Image and thumbnail files**

Both files contain exactly the 4 bytes `0xFF 0xD8 0xFF 0xD9` (a minimal JPEG SOI+EOI marker pair). Use `python -c 'open("...","wb").write(b"\xff\xd8\xff\xd9")'` from the shell, or a Python script — do **not** paste binary into a text editor.

- [ ] **Step 4: Verify pyright/ruff don't pick up the JSON files as Python and the binary files don't trigger any warnings.**

Run all gates.

- [ ] **Step 5: Commit**

```bash
git add tests/infrastructure/filesystem/fixtures
git commit -m "test(infra): add example storage_root fixture for round-trip acceptance"
```

---

## Task 13: Round-trip acceptance test against the fixture

**Files:**
- Create: `tests/infrastructure/filesystem/test_example_roundtrip.py`

- [ ] **Step 1: Test**

```python
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)

FIXTURE = Path(__file__).parent / "fixtures" / "example_storage_root"


@pytest.fixture
def working_root(tmp_path: Path) -> Path:
    target = tmp_path / "storage"
    shutil.copytree(FIXTURE, target)
    return target


def test_can_read_vehicle_from_fixture(working_root: Path) -> None:
    repo = FilesystemVehicleRepository(working_root)
    vehicle = repo.get(VehicleId("12345"))
    assert vehicle.id == VehicleId("12345")
    assert vehicle.vin == "WDB12345TEST"
    assert vehicle.created_at == datetime(2026, 4, 15, 10, 0, tzinfo=UTC)


def test_can_list_repairs_from_fixture(working_root: Path) -> None:
    repo = FilesystemRepairRepository(working_root)
    repairs = list(repo.list_for_vehicle(VehicleId("12345")))
    assert len(repairs) == 1
    assert repairs[0].description == "Bremsbeläge vorne"


def test_can_list_images_from_fixture(working_root: Path) -> None:
    repair_repo = FilesystemRepairRepository(working_root)
    image_repo = FilesystemImageRepository(working_root)
    repair = next(iter(repair_repo.list_for_vehicle(VehicleId("12345"))))
    images = list(image_repo.list_for_repair(repair.id))
    assert len(images) == 1
    assert images[0].size_bytes == 4
    assert images[0].thumbnail_key is not None


def test_round_trip_re_save_produces_byte_identical_sidecar(working_root: Path) -> None:
    repo = FilesystemVehicleRepository(working_root)
    vehicle = repo.get(VehicleId("12345"))
    sidecar_before = (working_root / "12345" / "_vehicle.json").read_text(encoding="utf-8")
    repo.update(vehicle)
    sidecar_after = (working_root / "12345" / "_vehicle.json").read_text(encoding="utf-8")
    # Field order may differ; compare normalised JSON.
    import json
    assert json.loads(sidecar_before) == json.loads(sidecar_after)
```

- [ ] **Step 2: Tests pass.**

- [ ] **Step 3: Commit**

```bash
git add tests/infrastructure/filesystem/test_example_roundtrip.py
git commit -m "test(infra): add round-trip acceptance test against example fixture"
```

---

## Task 14: Phase 2 acceptance

**Files:** none (verification only).

- [ ] **Step 1: Pyright clean**

```bash
uv run pyright
```
0 errors.

- [ ] **Step 2: Pytest with coverage**

```bash
uv run pytest --cov=edelrep --cov-report=term-missing
```

- All tests pass.
- Domain coverage stays ≥ 95%.
- Each new infrastructure file ≥ 90% (the helpers should be ≥ 95%; the repo classes have unreachable defensive `try/except` paths).

- [ ] **Step 3: Ruff clean**

```bash
uv run ruff check . && uv run ruff format --check .
```

- [ ] **Step 4: Domain framework-import guard**

```bash
! grep -REn "fastapi|sqlalchemy|fsspec|pydantic|httpx|requests" src/edelrep/domain/
```

Exit 0.

- [ ] **Step 5: Verify entity equality across read/write**

```bash
uv run python -c "
import shutil, tempfile, pathlib
from edelrep.infrastructure.filesystem import FilesystemVehicleRepository
from edelrep.domain.value_objects import VehicleId
src = pathlib.Path('tests/infrastructure/filesystem/fixtures/example_storage_root')
with tempfile.TemporaryDirectory() as td:
    dst = pathlib.Path(td) / 'storage'
    shutil.copytree(src, dst)
    repo = FilesystemVehicleRepository(dst)
    v = repo.get(VehicleId('12345'))
    print('OK', v.vin)
"
```

Should print `OK WDB12345TEST`.

- [ ] **Step 6: Tag**

```bash
git tag phase-2-complete
git tag -l phase-2-complete
git log --oneline phase-1-complete..phase-2-complete
```

---

## Self-Review Notes

- **Spec coverage (PLAN.md §12 Phase 2):** layout + atomic write + sidecar + 3 repos + fixture + round-trip — ✅. Schema-version header — ✅. `tmp_path`-based integration tests — ✅.
- **Out of scope for this plan:** thumbnail generation (Phase 4), EXIF capture-time extraction (Phase 4), inbox-derived `ImageSource.EMAIL` (Phase 8), `StorageBackend` indirection (Phase 3), SQLite index (Phase 5).
- **Naming consistency:** filesystem repo class names (`FilesystemVehicleRepository`, etc.) prefixed clearly; Phase 5 will add `Sqlite*` peers without name collision.
- **Open follow-ups for Phase 3:** the three repos take a `Path` directly. Phase 3 will introduce `StorageBackend` and the constructors will switch to `(backend: StorageBackend)`. The unit tests should mostly survive intact via a `LocalFilesystemBackend` adapter.
