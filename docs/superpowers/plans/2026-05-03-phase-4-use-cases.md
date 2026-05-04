# Phase 4 — Use Cases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the application layer — four orchestrating use cases (`UploadImageUseCase`, `ListRepairsUseCase`, `GetImageUseCase`, `SearchVehicleUseCase`) — composed entirely against domain ports, plus the EXIF + thumbnail processing helper and an in-memory `SearchIndex` adapter for testing and dev mode.

**Architecture:** New top-level package `src/edelrep/application/` containing the four use case classes. Each use case takes its required ports via `__init__` and exposes a single `execute(...)` method. EXIF/thumbnail logic lives separately in `src/edelrep/infrastructure/exif/pillow_processor.py` so use cases stay framework-light. The `InMemorySearchIndex` lives in `src/edelrep/infrastructure/search/` as a legitimate (non-persistent) adapter — Phase 5 adds the SQLite peer. Tests use lightweight in-memory port fakes from `tests/application/fakes.py`.

**Tech Stack:** Python 3.13, Pillow ≥ 11 (new runtime dep), pytest. No web framework yet (Phase 7).

**Definition of Done (PLAN.md §12 Phase 4):**
- All four use cases implemented with classes that accept ports as constructor dependencies.
- `UploadImageUseCase` correctly creates the on-disk layout per PLAN.md §6 (verified end-to-end against `LocalFilesystemBackend` + the three filesystem repositories).
- Pillow processor exposes `process_uploaded_image(raw_bytes) -> ProcessedImage` with rotated bytes, thumbnail bytes, and EXIF capture-time extraction.
- `InMemorySearchIndex` satisfies the `SearchIndex` Protocol.
- Use cases are I/O-free testable using port fakes (no filesystem in unit tests of `application/`).
- `uv run pyright`, `uv run pytest`, `uv run ruff check .` all green.
- Coverage stays ≥ 95% overall; every new file ≥ 90%.
- Tag `phase-4-complete`.

**Branch:** `phase-4-use-cases` (off `master` at `306d269`).

---

## File Structure

**Created:**

```
src/edelrep/application/
├── __init__.py                          # re-exports the four use cases
├── upload_image.py                      # UploadImageUseCase
├── list_repairs.py                      # ListRepairsUseCase
├── get_image.py                         # GetImageUseCase
└── search_vehicle.py                    # SearchVehicleUseCase

src/edelrep/infrastructure/exif/
├── __init__.py
└── pillow_processor.py                  # process_uploaded_image(...) -> ProcessedImage

src/edelrep/infrastructure/search/
├── __init__.py
└── in_memory.py                         # InMemorySearchIndex

tests/application/
├── __init__.py
├── fakes.py                             # InMemoryVehicleRepo, InMemoryRepairRepo, InMemoryImageRepo
├── conftest.py                          # fake-repo fixtures + pre-baked sample images
├── test_upload_image.py
├── test_list_repairs.py
├── test_get_image.py
└── test_search_vehicle.py

tests/infrastructure/exif/
├── __init__.py
└── test_pillow_processor.py

tests/infrastructure/search/
├── __init__.py
└── test_in_memory.py
```

**Modified:**

```
pyproject.toml                            # add Pillow
.gitignore                                # add *.cover (carry-over from Phase 3 review)
```

**Unchanged:** Domain layer, all Phase 2/3 infrastructure files.

---

## Design Notes

### Use case structure

```python
class UploadImageUseCase:
    def __init__(self, repair_repo: RepairRepository, image_repo: ImageRepository,
                 processor: ImageProcessor) -> None: ...

    def execute(self, *, repair_id: ULID, raw_bytes: bytes,
                filename: str, source: ImageSource = ImageSource.MANUAL) -> Image: ...
```

- One class per use case file.
- `__init__` documents required ports.
- `execute` is keyword-only for clarity at call sites.
- Domain entities returned directly. DTOs / response shapes are deferred to Phase 7 (web).

### `ImageProcessor` port

Use cases should not depend on Pillow directly. Introduce a lightweight `ImageProcessor` Protocol in the application layer (not domain — it's an application-layer concern, not a core invariant):

```python
@dataclass(frozen=True, slots=True)
class ProcessedImage:
    rotated_bytes: bytes
    thumbnail_bytes: bytes
    captured_at: datetime | None
    mime_type: str

class ImageProcessor(Protocol):
    def process(self, raw_bytes: bytes) -> ProcessedImage: ...
```

The Pillow-backed implementation lives in `infrastructure/exif/pillow_processor.py`.

### EXIF capture-time semantics

- Read tag `DateTimeOriginal` (0x9003) from `Image.getexif()`.
- Format: `"YYYY:MM:DD HH:MM:SS"`. Parse with `datetime.strptime(s, "%Y:%m:%d %H:%M:%S")`.
- The result is **timezone-naive**. Per PLAN.md §2 (Swiss workshop, V1) — treat as **UTC**. This is documented in the processor's docstring and a unit test asserts the conversion.
- If the tag is absent or unparseable: return `None`.

### Thumbnail policy

- Maximum dimensions 256 × 256, aspect ratio preserved (`Image.thumbnail()`).
- Output format: same as input mime type when supported (JPEG, PNG, WebP). Default to JPEG quality 85 if input is uncertain.
- For V1 we accept JPEG only as a hard requirement; PNG/WebP work but aren't tested exhaustively.

### EXIF orientation normalisation

- `ImageOps.exif_transpose(img)` returns a new image with the orientation applied and the EXIF orientation tag stripped.
- Re-encode the rotated image at original quality (JPEG quality 95 by default) so callers store the corrected pixels.

### `UploadImageUseCase` flow

1. Verify repair exists: `repair = repair_repo.get(repair_id)` → propagates `RepairNotFound`.
2. `processed = processor.process(raw_bytes)` → rotated bytes, thumb bytes, captured_at, mime_type.
3. Construct `Image` entity with `storage_key=""` placeholder (filled by repository on read).
4. `image_repo.save(image, raw_bytes=processed.rotated_bytes, thumbnail_bytes=processed.thumbnail_bytes)`.
5. `image_repo.get(image.id)` to return the populated entity (storage_key, thumbnail_key, accurate size_bytes from disk).
6. Return the populated entity.

### `GetImageUseCase`

Composes `ImageRepository` + `StorageBackend`:

```python
class GetImageUseCase:
    def __init__(self, image_repo: ImageRepository, backend: StorageBackend) -> None: ...

    def execute(self, image_id: ULID) -> tuple[Image, bytes]:
        image = self.image_repo.get(image_id)
        return image, self.backend.read_bytes(image.storage_key)
```

### `ListRepairsUseCase`

Validates the vehicle exists, then delegates to `repair_repo.list_for_vehicle(vehicle_id)` (returns newest-first per Phase 2 contract).

```python
class ListRepairsUseCase:
    def __init__(self, vehicle_repo: VehicleRepository, repair_repo: RepairRepository) -> None: ...

    def execute(self, vehicle_id: VehicleId) -> list[Repair]:
        if not self.vehicle_repo.exists(vehicle_id):
            raise VehicleNotFound(vehicle_id.registration_number)
        return list(self.repair_repo.list_for_vehicle(vehicle_id))
```

### `SearchVehicleUseCase`

Thin wrapper. Reason it exists: the web layer should call use cases, not ports directly. Future search refinements (relevance scoring, filtering) live here.

```python
class SearchVehicleUseCase:
    def __init__(self, search_index: SearchIndex) -> None: ...

    def execute(self, query: str, limit: int = 20) -> list[Vehicle]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        return list(self.search_index.search_vehicles(query, limit=limit))
```

### `InMemorySearchIndex`

A dict-backed implementation of the `SearchIndex` Protocol. Search is naive substring-match across `registration_number`, `vin`, and `description`. Useful for tests AND for dev composition root before Phase 5 SQLite arrives.

```python
class InMemorySearchIndex:
    def __init__(self) -> None: ...
    def search_vehicles(self, query: str, limit: int = 20) -> list[Vehicle]: ...
    def upsert_vehicle(self, vehicle: Vehicle) -> None: ...
    def remove_vehicle(self, vehicle_id: VehicleId) -> None: ...
    def clear(self) -> None: ...
```

Empty query returns empty list (not all vehicles) — Phase 5 SQLite will follow the same contract.

### Test fakes

`tests/application/fakes.py` exposes three classes implementing the repository ports as in-memory dicts. They are intentionally **dumb** (no validation, no error injection) — they exist to let use case tests focus on orchestration. Tests that need to assert "upload writes correct layout" are integration tests against the real `LocalFilesystemBackend` + `Filesystem*Repository` stack, kept under `tests/application/` but in `test_upload_image_integration.py` (one file).

---

## Task 1: Add Pillow dependency

**Files:** `pyproject.toml`, `.gitignore`

- [ ] **Step 1: Add `Pillow>=11.0.0` to runtime deps**

Edit `pyproject.toml`. Change:

```toml
dependencies = [
    "fsspec>=2024.0.0",
    "python-ulid>=3.0.0",
]
```

to:

```toml
dependencies = [
    "Pillow>=11.0.0",
    "fsspec>=2024.0.0",
    "python-ulid>=3.0.0",
]
```

(Capital `P` matches PyPI; uv normalises to lowercase internally.)

- [ ] **Step 2: Append `*.cover` to `.gitignore`**

Phase 3 review noted these artefacts get generated by pytest-cov in `src/`. Keep them out of the repo.

Edit `.gitignore`. Find the test/coverage section (looks like):

```
.pytest_cache/
.coverage
.coverage.*
htmlcov/
```

Add `*.cover` and remove any committed `.cover` files (a follow-up cleanup):

```bash
git rm --cached -f $(git ls-files | grep '\.cover$') 2>/dev/null || true
```

(That last command is a no-op if no `.cover` files were committed.)

- [ ] **Step 3: Sync deps**

```bash
uv sync
```

- [ ] **Step 4: Smoke check**

```bash
uv run python -c "from PIL import Image, ImageOps, ExifTags; print(Image.__version__)"
```

Expected: prints a version like `11.x` or higher (or `12.x` etc).

- [ ] **Step 5: Gates green**

```bash
uv run pyright
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

233 tests still pass.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .gitignore
git commit -m "chore(deps): add Pillow and ignore *.cover artefacts"
```

---

## Task 2: Scaffold application + exif + search packages

**Files:**
- Create: `src/edelrep/application/__init__.py` (1-byte marker; filled in Task 10)
- Create: `src/edelrep/infrastructure/exif/__init__.py`
- Create: `src/edelrep/infrastructure/search/__init__.py`
- Create: `tests/application/__init__.py`
- Create: `tests/infrastructure/exif/__init__.py`
- Create: `tests/infrastructure/search/__init__.py`

- [ ] **Step 1: Create six 1-byte marker files**

- [ ] **Step 2: Pyright clean**

- [ ] **Step 3: Commit**

```bash
git add src/edelrep/application src/edelrep/infrastructure/exif src/edelrep/infrastructure/search \
        tests/application tests/infrastructure/exif tests/infrastructure/search
git commit -m "feat: scaffold application, exif, and search subpackages"
```

---

## Task 3: `PillowImageProcessor` (TDD)

**Files:**
- Create: `tests/infrastructure/exif/test_pillow_processor.py`
- Create: `src/edelrep/infrastructure/exif/pillow_processor.py`

- [ ] **Step 1: Failing tests**

The tests need real bytes. Use Pillow itself in the test setup to generate synthetic JPEGs (this is OK — production code uses Pillow too).

```python
import io
from datetime import UTC, datetime

import piexif  # IF available, else use PIL.Image.Exif directly
import pytest
from PIL import ExifTags, Image

from edelrep.infrastructure.exif.pillow_processor import (
    PillowImageProcessor,
    ProcessedImage,
)


def _make_jpeg_bytes(
    *,
    size: tuple[int, int] = (640, 480),
    orientation: int = 1,
    capture_time: str | None = None,
) -> bytes:
    img = Image.new("RGB", size, color=(123, 200, 50))
    exif = img.getexif()
    if orientation != 1:
        exif[ExifTags.Base.Orientation.value] = orientation
    if capture_time is not None:
        # Tag 36867 = DateTimeOriginal. PIL stores under the ExifIFD; using the
        # main exif dict is enough for our extractor when paired with PIL's
        # default save behaviour, which propagates known tags to the right IFD.
        exif[ExifTags.Base.DateTimeOriginal.value] = capture_time
        exif[ExifTags.Base.DateTime.value] = capture_time
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif, quality=95)
    return buf.getvalue()


def test_process_returns_rotated_and_thumbnail_bytes() -> None:
    raw = _make_jpeg_bytes(size=(800, 600))
    processor = PillowImageProcessor()
    result = processor.process(raw)

    assert isinstance(result, ProcessedImage)
    assert len(result.rotated_bytes) > 0
    assert len(result.thumbnail_bytes) > 0
    assert result.thumbnail_bytes != result.rotated_bytes


def test_thumbnail_fits_within_max_dimensions() -> None:
    raw = _make_jpeg_bytes(size=(2000, 1500))
    processor = PillowImageProcessor()
    result = processor.process(raw)

    with Image.open(io.BytesIO(result.thumbnail_bytes)) as thumb:
        assert thumb.width <= 256
        assert thumb.height <= 256


def test_thumbnail_preserves_aspect_ratio() -> None:
    raw = _make_jpeg_bytes(size=(2000, 1000))  # 2:1
    processor = PillowImageProcessor()
    result = processor.process(raw)

    with Image.open(io.BytesIO(result.thumbnail_bytes)) as thumb:
        # 2:1 source → 256x128 thumbnail
        assert thumb.width == 256
        assert thumb.height == 128


def test_process_extracts_capture_time_as_utc() -> None:
    raw = _make_jpeg_bytes(capture_time="2026:05:03 14:30:00")
    processor = PillowImageProcessor()
    result = processor.process(raw)

    assert result.captured_at == datetime(2026, 5, 3, 14, 30, 0, tzinfo=UTC)


def test_process_returns_none_capture_time_when_absent() -> None:
    raw = _make_jpeg_bytes()  # no DateTimeOriginal
    processor = PillowImageProcessor()
    result = processor.process(raw)

    assert result.captured_at is None


def test_process_returns_none_capture_time_when_unparseable() -> None:
    raw = _make_jpeg_bytes(capture_time="not-a-date")
    processor = PillowImageProcessor()
    result = processor.process(raw)

    assert result.captured_at is None


def test_rotated_bytes_strip_orientation_tag() -> None:
    # Orientation 6 = rotated 90° CW. After exif_transpose, orientation should be 1 (normal).
    raw = _make_jpeg_bytes(size=(640, 480), orientation=6)
    processor = PillowImageProcessor()
    result = processor.process(raw)

    with Image.open(io.BytesIO(result.rotated_bytes)) as rotated:
        exif = rotated.getexif()
        # After transpose, the image should either have no orientation tag or it should be 1.
        orientation = exif.get(ExifTags.Base.Orientation.value, 1)
        assert orientation == 1
        # Width/height swapped due to 90° rotation
        assert rotated.width == 480
        assert rotated.height == 640


def test_mime_type_is_image_jpeg_for_jpeg_input() -> None:
    raw = _make_jpeg_bytes()
    processor = PillowImageProcessor()
    result = processor.process(raw)
    assert result.mime_type == "image/jpeg"


def test_process_rejects_non_image_bytes() -> None:
    processor = PillowImageProcessor()
    with pytest.raises(ValueError, match="image"):
        processor.process(b"not an image at all")
```

If `piexif` is not installed: drop that import and rely on PIL's `getexif()` direct dict access. The tests above already use PIL directly.

- [ ] **Step 2: Verify failing**

- [ ] **Step 3: Implementation**

Create `src/edelrep/infrastructure/exif/pillow_processor.py`:

```python
import io
from dataclasses import dataclass
from datetime import UTC, datetime

from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError

_THUMBNAIL_MAX_SIZE = (256, 256)
_JPEG_QUALITY = 95
_THUMB_QUALITY = 85
_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"

_MIME_BY_PIL_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    rotated_bytes: bytes
    thumbnail_bytes: bytes
    captured_at: datetime | None
    mime_type: str


class PillowImageProcessor:
    """Pillow-backed implementation of the application ImageProcessor port.

    - Applies EXIF orientation transpose so stored pixels are upright.
    - Generates a max-256x256 aspect-preserved thumbnail (JPEG quality 85).
    - Extracts ``DateTimeOriginal`` and treats it as UTC (V1 single-workshop
      assumption per PLAN.md §2).
    """

    def process(self, raw_bytes: bytes) -> ProcessedImage:
        try:
            with Image.open(io.BytesIO(raw_bytes)) as src:
                src.load()
                fmt = (src.format or "JPEG").upper()
                captured_at = _extract_capture_time(src)
                rotated = ImageOps.exif_transpose(src)
                if rotated is None:
                    rotated = src.copy()
                rotated_bytes = _encode(rotated, fmt, _JPEG_QUALITY)
                thumb = rotated.copy()
                thumb.thumbnail(_THUMBNAIL_MAX_SIZE)
                thumbnail_bytes = _encode(thumb, fmt, _THUMB_QUALITY)
        except UnidentifiedImageError as exc:
            raise ValueError(f"input is not a recognised image: {exc}") from exc
        return ProcessedImage(
            rotated_bytes=rotated_bytes,
            thumbnail_bytes=thumbnail_bytes,
            captured_at=captured_at,
            mime_type=_MIME_BY_PIL_FORMAT.get(fmt, "application/octet-stream"),
        )


def _encode(img: Image.Image, fmt: str, quality: int) -> bytes:
    out = io.BytesIO()
    if fmt == "JPEG" and img.mode != "RGB":
        img = img.convert("RGB")
    save_kwargs: dict[str, object] = {}
    if fmt == "JPEG":
        save_kwargs["quality"] = quality
    img.save(out, format=fmt, **save_kwargs)
    return out.getvalue()


def _extract_capture_time(img: Image.Image) -> datetime | None:
    try:
        exif = img.getexif()
    except Exception:
        return None
    if not exif:
        return None
    raw = exif.get(ExifTags.Base.DateTimeOriginal.value)
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("ascii", errors="ignore")
    try:
        naive = datetime.strptime(str(raw), _DATETIME_FORMAT)
    except ValueError:
        return None
    return naive.replace(tzinfo=UTC)
```

If pyright complains about `ExifTags.Base` being untyped (Pillow ships partial stubs), suppress with a per-line comment. If ruff complains about bare `except Exception`, narrow to `(KeyError, AttributeError)` or whatever fits.

- [ ] **Step 4: Tests pass**

If `test_rotated_bytes_strip_orientation_tag` fails because the re-saved JPEG doesn't carry the EXIF block when the orientation was stripped, that's fine — the test should still pass (orientation defaults to 1 / normal). Adjust the test assertion to handle the "no exif" case if needed.

- [ ] **Step 5: Gates clean**

- [ ] **Step 6: Commit**

```bash
git add src/edelrep/infrastructure/exif/pillow_processor.py \
        tests/infrastructure/exif/test_pillow_processor.py
git commit -m "feat(infra): add PillowImageProcessor (rotate, thumbnail, capture-time extraction)"
```

---

## Task 4: `InMemorySearchIndex` (TDD)

**Files:**
- Create: `tests/infrastructure/search/test_in_memory.py`
- Create: `src/edelrep/infrastructure/search/in_memory.py`

- [ ] **Step 1: Failing test**

```python
from datetime import UTC, datetime

import pytest

from edelrep.domain.entities import Vehicle
from edelrep.domain.ports import SearchIndex
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.search.in_memory import InMemorySearchIndex


def _v(reg: str, vin: str = "X", description: str = "") -> Vehicle:
    return Vehicle(
        id=VehicleId(reg),
        vin=vin or None,
        description=description or None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_satisfies_protocol() -> None:
    idx: SearchIndex = InMemorySearchIndex()
    assert isinstance(idx, SearchIndex)


def test_empty_query_returns_empty_list() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345"))
    assert list(idx.search_vehicles("")) == []


def test_search_by_registration_number_substring() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345"))
    idx.upsert_vehicle(_v("99999"))
    results = list(idx.search_vehicles("123"))
    assert [v.id.registration_number for v in results] == ["12345"]


def test_search_by_vin_substring() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345", vin="WDB123ABC"))
    idx.upsert_vehicle(_v("99999", vin="VFX9999"))
    results = list(idx.search_vehicles("WDB"))
    assert [v.id.registration_number for v in results] == ["12345"]


def test_search_by_description_substring_case_insensitive() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345", description="Kran 4-achsig"))
    idx.upsert_vehicle(_v("99999", description="Lieferwagen"))
    results = list(idx.search_vehicles("KRAN"))
    assert [v.id.registration_number for v in results] == ["12345"]


def test_search_respects_limit() -> None:
    idx = InMemorySearchIndex()
    for i in range(5):
        idx.upsert_vehicle(_v(f"1234{i}"))
    results = list(idx.search_vehicles("1234", limit=3))
    assert len(results) == 3


def test_upsert_replaces_existing() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345", description="old"))
    idx.upsert_vehicle(_v("12345", description="new"))
    results = list(idx.search_vehicles("new"))
    assert len(results) == 1
    assert results[0].description == "new"


def test_remove_vehicle() -> None:
    idx = InMemorySearchIndex()
    vid = VehicleId("12345")
    idx.upsert_vehicle(_v("12345"))
    idx.remove_vehicle(vid)
    assert list(idx.search_vehicles("123")) == []


def test_remove_missing_is_noop() -> None:
    idx = InMemorySearchIndex()
    idx.remove_vehicle(VehicleId("never-existed"))  # no exception


def test_clear_empties_index() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345"))
    idx.upsert_vehicle(_v("99999"))
    idx.clear()
    assert list(idx.search_vehicles("123")) == []
    assert list(idx.search_vehicles("999")) == []
```

- [ ] **Step 2: Verify failing**

- [ ] **Step 3: Implementation**

```python
from collections.abc import Iterable

from edelrep.domain.entities import Vehicle
from edelrep.domain.value_objects import VehicleId


class InMemorySearchIndex:
    """Dict-backed SearchIndex implementation.

    Search is case-insensitive substring match across registration_number,
    vin, and description. Empty queries return an empty list.

    Useful both as a test fake and as a dev-mode adapter until Phase 5
    SQLite + FTS5 ships.
    """

    def __init__(self) -> None:
        self._rows: dict[VehicleId, Vehicle] = {}

    def search_vehicles(self, query: str, limit: int = 20) -> Iterable[Vehicle]:
        if not query:
            return []
        needle = query.lower()
        results: list[Vehicle] = []
        for vehicle in self._rows.values():
            haystack = " ".join(
                str(part) for part in (
                    vehicle.id.registration_number,
                    vehicle.vin or "",
                    vehicle.description or "",
                )
            ).lower()
            if needle in haystack:
                results.append(vehicle)
            if len(results) >= limit:
                break
        return results

    def upsert_vehicle(self, vehicle: Vehicle) -> None:
        self._rows[vehicle.id] = vehicle

    def remove_vehicle(self, vehicle_id: VehicleId) -> None:
        self._rows.pop(vehicle_id, None)

    def clear(self) -> None:
        self._rows.clear()
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Gates clean**

- [ ] **Step 6: Commit**

```bash
git add src/edelrep/infrastructure/search/in_memory.py \
        tests/infrastructure/search/test_in_memory.py
git commit -m "feat(infra): add InMemorySearchIndex implementing SearchIndex protocol"
```

---

## Task 5: Test fakes for repository ports

**Files:**
- Create: `tests/application/fakes.py`
- Create: `tests/application/conftest.py`

- [ ] **Step 1: Create fakes**

`tests/application/fakes.py`:

```python
from collections.abc import Iterable

from ulid import ULID

from edelrep.domain.entities import Image, Repair, Vehicle
from edelrep.domain.exceptions import (
    DuplicateRepair,
    DuplicateVehicle,
    ImageNotFound,
    RepairNotFound,
    VehicleNotFound,
)
from edelrep.domain.value_objects import VehicleId


class InMemoryVehicleRepo:
    def __init__(self) -> None:
        self._store: dict[VehicleId, Vehicle] = {}

    def get(self, vehicle_id: VehicleId) -> Vehicle:
        try:
            return self._store[vehicle_id]
        except KeyError as exc:
            raise VehicleNotFound(vehicle_id.registration_number) from exc

    def save(self, vehicle: Vehicle) -> None:
        if vehicle.id in self._store:
            raise DuplicateVehicle(vehicle.id.registration_number)
        self._store[vehicle.id] = vehicle

    def update(self, vehicle: Vehicle) -> None:
        if vehicle.id not in self._store:
            raise VehicleNotFound(vehicle.id.registration_number)
        self._store[vehicle.id] = vehicle

    def list_all(self) -> Iterable[Vehicle]:
        return list(self._store.values())

    def exists(self, vehicle_id: VehicleId) -> bool:
        return vehicle_id in self._store


class InMemoryRepairRepo:
    def __init__(self) -> None:
        self._store: dict[ULID, Repair] = {}

    def get(self, repair_id: ULID) -> Repair:
        try:
            return self._store[repair_id]
        except KeyError as exc:
            raise RepairNotFound(repair_id) from exc

    def save(self, repair: Repair) -> None:
        for existing in self._store.values():
            if (
                existing.vehicle_id == repair.vehicle_id
                and existing.date == repair.date
                and existing.description == repair.description
            ):
                raise DuplicateRepair(
                    repair.vehicle_id.registration_number,
                    f"{repair.date.isoformat()}__{repair.description}",
                )
        self._store[repair.id] = repair

    def update(self, repair: Repair) -> None:
        if repair.id not in self._store:
            raise RepairNotFound(repair.id)
        self._store[repair.id] = repair

    def list_for_vehicle(self, vehicle_id: VehicleId) -> Iterable[Repair]:
        return sorted(
            (r for r in self._store.values() if r.vehicle_id == vehicle_id),
            key=lambda r: r.date,
            reverse=True,
        )


class InMemoryImageRepo:
    def __init__(self) -> None:
        self._store: dict[ULID, tuple[Image, bytes, bytes | None]] = {}

    def get(self, image_id: ULID) -> Image:
        try:
            return self._store[image_id][0]
        except KeyError as exc:
            raise ImageNotFound(image_id) from exc

    def save(
        self,
        image: Image,
        *,
        raw_bytes: bytes,
        thumbnail_bytes: bytes | None = None,
    ) -> None:
        # The fake stores bytes alongside, mimicking what FilesystemImageRepository does.
        # storage_key gets a synthetic value reflecting the in-memory layout.
        synthetic_key = f"<memory>/{image.repair_id}/{image.id}.{image.filename.rsplit('.', 1)[-1]}"
        synthetic_thumb = f"{synthetic_key}.thumb" if thumbnail_bytes is not None else None
        populated = Image(
            id=image.id,
            repair_id=image.repair_id,
            storage_key=synthetic_key,
            thumbnail_key=synthetic_thumb,
            filename=image.filename,
            mime_type=image.mime_type,
            size_bytes=len(raw_bytes),
            source=image.source,
            uploaded_at=image.uploaded_at,
            captured_at=image.captured_at,
        )
        self._store[image.id] = (populated, raw_bytes, thumbnail_bytes)

    def list_for_repair(self, repair_id: ULID) -> Iterable[Image]:
        return [entry[0] for entry in self._store.values() if entry[0].repair_id == repair_id]

    # Convenience helpers for use-case integration tests:
    def raw_bytes_for(self, image_id: ULID) -> bytes:
        return self._store[image_id][1]

    def thumbnail_bytes_for(self, image_id: ULID) -> bytes | None:
        return self._store[image_id][2]
```

- [ ] **Step 2: Add fixtures**

`tests/application/conftest.py`:

```python
from datetime import UTC, date, datetime

import pytest
from ulid import ULID

from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.value_objects import VehicleId

from .fakes import InMemoryImageRepo, InMemoryRepairRepo, InMemoryVehicleRepo


@pytest.fixture
def vehicle_repo() -> InMemoryVehicleRepo:
    return InMemoryVehicleRepo()


@pytest.fixture
def repair_repo() -> InMemoryRepairRepo:
    return InMemoryRepairRepo()


@pytest.fixture
def image_repo() -> InMemoryImageRepo:
    return InMemoryImageRepo()


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
```

- [ ] **Step 3: Verify type compliance**

The fakes must satisfy `VehicleRepository` / `RepairRepository` / `ImageRepository` Protocols. Add a small test in `tests/application/test_fakes_protocols.py`:

```python
import pytest

from edelrep.domain.ports import (
    ImageRepository,
    RepairRepository,
    VehicleRepository,
)

from .fakes import InMemoryImageRepo, InMemoryRepairRepo, InMemoryVehicleRepo


def test_vehicle_repo_satisfies_protocol() -> None:
    repo: VehicleRepository = InMemoryVehicleRepo()
    assert isinstance(repo, VehicleRepository)


def test_repair_repo_satisfies_protocol() -> None:
    repo: RepairRepository = InMemoryRepairRepo()
    assert isinstance(repo, RepairRepository)


def test_image_repo_satisfies_protocol() -> None:
    repo: ImageRepository = InMemoryImageRepo()
    assert isinstance(repo, ImageRepository)
```

- [ ] **Step 4: Gates clean**

- [ ] **Step 5: Commit**

```bash
git add tests/application/fakes.py tests/application/conftest.py tests/application/test_fakes_protocols.py
git commit -m "test(application): add in-memory port fakes and protocol-compliance test"
```

---

## Task 6: `ListRepairsUseCase` (TDD)

**Files:**
- Create: `tests/application/test_list_repairs.py`
- Create: `src/edelrep/application/list_repairs.py`

- [ ] **Step 1: Failing tests**

```python
from datetime import UTC, date, datetime

import pytest
from ulid import ULID

from edelrep.application.list_repairs import ListRepairsUseCase
from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.exceptions import VehicleNotFound
from edelrep.domain.value_objects import VehicleId

from .fakes import InMemoryRepairRepo, InMemoryVehicleRepo


def test_returns_empty_for_vehicle_with_no_repairs(
    vehicle_repo: InMemoryVehicleRepo,
    repair_repo: InMemoryRepairRepo,
    sample_vehicle: Vehicle,
) -> None:
    vehicle_repo.save(sample_vehicle)
    use_case = ListRepairsUseCase(vehicle_repo, repair_repo)
    assert use_case.execute(sample_vehicle.id) == []


def test_returns_repairs_newest_first(
    vehicle_repo: InMemoryVehicleRepo,
    repair_repo: InMemoryRepairRepo,
    sample_vehicle: Vehicle,
) -> None:
    vehicle_repo.save(sample_vehicle)
    older = Repair(
        id=ULID(),
        vehicle_id=sample_vehicle.id,
        date=date(2026, 1, 1),
        description="old",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = Repair(
        id=ULID(),
        vehicle_id=sample_vehicle.id,
        date=date(2026, 5, 1),
        description="new",
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    repair_repo.save(older)
    repair_repo.save(newer)

    use_case = ListRepairsUseCase(vehicle_repo, repair_repo)
    results = use_case.execute(sample_vehicle.id)
    assert [r.description for r in results] == ["new", "old"]


def test_raises_when_vehicle_missing(
    vehicle_repo: InMemoryVehicleRepo,
    repair_repo: InMemoryRepairRepo,
) -> None:
    use_case = ListRepairsUseCase(vehicle_repo, repair_repo)
    with pytest.raises(VehicleNotFound):
        use_case.execute(VehicleId("99999"))
```

- [ ] **Step 2: Verify failing**

- [ ] **Step 3: Implementation**

```python
from edelrep.domain.entities import Repair
from edelrep.domain.exceptions import VehicleNotFound
from edelrep.domain.ports import RepairRepository, VehicleRepository
from edelrep.domain.value_objects import VehicleId


class ListRepairsUseCase:
    """List a vehicle's repairs, newest first."""

    def __init__(
        self,
        vehicle_repo: VehicleRepository,
        repair_repo: RepairRepository,
    ) -> None:
        self._vehicle_repo = vehicle_repo
        self._repair_repo = repair_repo

    def execute(self, vehicle_id: VehicleId) -> list[Repair]:
        if not self._vehicle_repo.exists(vehicle_id):
            raise VehicleNotFound(vehicle_id.registration_number)
        return list(self._repair_repo.list_for_vehicle(vehicle_id))
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Gates clean**

- [ ] **Step 6: Commit**

```bash
git add src/edelrep/application/list_repairs.py tests/application/test_list_repairs.py
git commit -m "feat(application): add ListRepairsUseCase"
```

---

## Task 7: `GetImageUseCase` (TDD)

**Files:**
- Create: `tests/application/test_get_image.py`
- Create: `src/edelrep/application/get_image.py`

- [ ] **Step 1: Failing tests**

The use case takes both `ImageRepository` and `StorageBackend`. The test uses the fake image repo plus a stub backend that returns bytes from a dict.

```python
import pytest
from ulid import ULID

from edelrep.application.get_image import GetImageUseCase
from edelrep.domain.exceptions import ImageNotFound
from edelrep.domain.entities import Image, ImageSource
from datetime import UTC, datetime

from .fakes import InMemoryImageRepo


class _StubBackend:
    def __init__(self, files: dict[str, bytes]) -> None:
        self._files = files

    def read_bytes(self, key: str) -> bytes:
        return self._files[key]

    def write_bytes(self, key: str, data: bytes) -> None:  # pragma: no cover
        self._files[key] = data

    def open_read(self, key: str):  # pragma: no cover
        import io

        return io.BytesIO(self._files[key])

    def delete(self, key: str) -> None:  # pragma: no cover
        self._files.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._files

    def list_prefix(self, prefix: str):  # pragma: no cover
        return [k for k in self._files if k.startswith(prefix)]


def _img(image_id: ULID, repair_id: ULID, key: str) -> Image:
    return Image(
        id=image_id,
        repair_id=repair_id,
        storage_key=key,
        thumbnail_key=None,
        filename="x.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime(2026, 5, 3, tzinfo=UTC),
        captured_at=None,
    )


def test_returns_image_and_bytes() -> None:
    repair_id = ULID()
    image_id = ULID()
    storage_key = "12345/2026-05-03__brakes/0001_test.jpg"
    repo = InMemoryImageRepo()
    repo.save(
        _img(image_id, repair_id, storage_key),
        raw_bytes=b"\xff\xd8\xff\xd9",
    )
    fetched = repo.get(image_id)
    backend = _StubBackend({fetched.storage_key: b"\xff\xd8\xff\xd9"})

    use_case = GetImageUseCase(repo, backend)
    image, raw = use_case.execute(image_id)

    assert image.id == image_id
    assert raw == b"\xff\xd8\xff\xd9"


def test_raises_when_missing() -> None:
    repo = InMemoryImageRepo()
    backend = _StubBackend({})
    use_case = GetImageUseCase(repo, backend)
    with pytest.raises(ImageNotFound):
        use_case.execute(ULID())
```

- [ ] **Step 2: Verify failing**

- [ ] **Step 3: Implementation**

```python
from ulid import ULID

from edelrep.domain.entities import Image
from edelrep.domain.ports import ImageRepository, StorageBackend


class GetImageUseCase:
    """Fetch an image entity and its raw bytes for download."""

    def __init__(self, image_repo: ImageRepository, backend: StorageBackend) -> None:
        self._image_repo = image_repo
        self._backend = backend

    def execute(self, image_id: ULID) -> tuple[Image, bytes]:
        image = self._image_repo.get(image_id)
        return image, self._backend.read_bytes(image.storage_key)
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Gates clean**

- [ ] **Step 6: Commit**

```bash
git add src/edelrep/application/get_image.py tests/application/test_get_image.py
git commit -m "feat(application): add GetImageUseCase"
```

---

## Task 8: `SearchVehicleUseCase` (TDD)

**Files:**
- Create: `tests/application/test_search_vehicle.py`
- Create: `src/edelrep/application/search_vehicle.py`

- [ ] **Step 1: Failing tests**

```python
from datetime import UTC, datetime

import pytest

from edelrep.application.search_vehicle import SearchVehicleUseCase
from edelrep.domain.entities import Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.search.in_memory import InMemorySearchIndex


def _v(reg: str) -> Vehicle:
    return Vehicle(
        id=VehicleId(reg),
        vin="W",
        description="x",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_search_returns_matching_vehicles() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345"))
    idx.upsert_vehicle(_v("67890"))
    use_case = SearchVehicleUseCase(idx)
    results = use_case.execute("123")
    assert [v.id.registration_number for v in results] == ["12345"]


def test_empty_query_returns_empty_list() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345"))
    use_case = SearchVehicleUseCase(idx)
    assert use_case.execute("") == []


def test_limit_must_be_positive() -> None:
    idx = InMemorySearchIndex()
    use_case = SearchVehicleUseCase(idx)
    with pytest.raises(ValueError, match="limit"):
        use_case.execute("any", limit=0)


def test_limit_passes_through_to_index() -> None:
    idx = InMemorySearchIndex()
    for i in range(5):
        idx.upsert_vehicle(_v(f"1234{i}"))
    use_case = SearchVehicleUseCase(idx)
    results = use_case.execute("1234", limit=2)
    assert len(results) == 2
```

- [ ] **Step 2: Verify failing**

- [ ] **Step 3: Implementation**

```python
from edelrep.domain.entities import Vehicle
from edelrep.domain.ports import SearchIndex


class SearchVehicleUseCase:
    """Search vehicles by registration number, VIN, or description."""

    def __init__(self, search_index: SearchIndex) -> None:
        self._search_index = search_index

    def execute(self, query: str, limit: int = 20) -> list[Vehicle]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        return list(self._search_index.search_vehicles(query, limit=limit))
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Gates clean**

- [ ] **Step 6: Commit**

```bash
git add src/edelrep/application/search_vehicle.py tests/application/test_search_vehicle.py
git commit -m "feat(application): add SearchVehicleUseCase"
```

---

## Task 9: `UploadImageUseCase` (TDD) — most complex

**Files:**
- Create: `tests/application/test_upload_image.py`
- Create: `tests/application/test_upload_image_integration.py`
- Create: `src/edelrep/application/upload_image.py`

The use case requires an `ImageProcessor` Protocol. Define it inline with the use case (not separately).

- [ ] **Step 1: Unit-test failing tests** (`test_upload_image.py`)

The unit test uses a `_StubProcessor` rather than the real Pillow processor — keeps the use case test framework-light:

```python
from datetime import UTC, datetime

import pytest
from ulid import ULID

from edelrep.application.upload_image import (
    ProcessedImage,
    UploadImageUseCase,
)
from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
from edelrep.domain.exceptions import RepairNotFound

from .fakes import InMemoryImageRepo, InMemoryRepairRepo


class _StubProcessor:
    def __init__(self, *, captured_at: datetime | None = None) -> None:
        self._captured_at = captured_at

    def process(self, raw_bytes: bytes) -> ProcessedImage:
        return ProcessedImage(
            rotated_bytes=b"ROTATED:" + raw_bytes,
            thumbnail_bytes=b"THUMB:" + raw_bytes,
            captured_at=self._captured_at,
            mime_type="image/jpeg",
        )


def test_upload_returns_persisted_image(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
) -> None:
    repair_repo.save(sample_repair)
    use_case = UploadImageUseCase(repair_repo, image_repo, _StubProcessor())
    image = use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"raw",
        filename="foo.jpg",
    )
    assert image.repair_id == sample_repair.id
    assert image.size_bytes == len(b"ROTATED:raw")
    # Persisted via fake → storage_key should be populated.
    assert image.storage_key
    assert image_repo.get(image.id).storage_key == image.storage_key


def test_upload_writes_thumbnail_bytes(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_repair: Repair,
) -> None:
    repair_repo.save(sample_repair)
    use_case = UploadImageUseCase(repair_repo, image_repo, _StubProcessor())
    image = use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"raw",
        filename="foo.jpg",
    )
    assert image_repo.thumbnail_bytes_for(image.id) == b"THUMB:raw"


def test_upload_propagates_capture_time(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_repair: Repair,
) -> None:
    repair_repo.save(sample_repair)
    captured = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)
    use_case = UploadImageUseCase(
        repair_repo, image_repo, _StubProcessor(captured_at=captured)
    )
    image = use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"raw",
        filename="foo.jpg",
    )
    assert image.captured_at == captured


def test_upload_default_source_is_manual(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_repair: Repair,
) -> None:
    repair_repo.save(sample_repair)
    use_case = UploadImageUseCase(repair_repo, image_repo, _StubProcessor())
    image = use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"raw",
        filename="foo.jpg",
    )
    assert image.source == ImageSource.MANUAL


def test_upload_explicit_source(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_repair: Repair,
) -> None:
    repair_repo.save(sample_repair)
    use_case = UploadImageUseCase(repair_repo, image_repo, _StubProcessor())
    image = use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"raw",
        filename="foo.jpg",
        source=ImageSource.EMAIL,
    )
    assert image.source == ImageSource.EMAIL


def test_upload_raises_when_repair_missing(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
) -> None:
    use_case = UploadImageUseCase(repair_repo, image_repo, _StubProcessor())
    with pytest.raises(RepairNotFound):
        use_case.execute(
            repair_id=ULID(),
            raw_bytes=b"raw",
            filename="foo.jpg",
        )
```

- [ ] **Step 2: Integration test** (`test_upload_image_integration.py`)

Verifies the use case correctly produces the on-disk layout when wired with the real `LocalFilesystemBackend` + `Filesystem*Repository` stack and the real `PillowImageProcessor`. This is the "DoD: korrekte Ordnerstruktur" check.

```python
import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image as PILImage

from edelrep.application.upload_image import UploadImageUseCase
from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.exif.pillow_processor import PillowImageProcessor
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.storage import LocalFilesystemBackend


def _real_jpeg_bytes() -> bytes:
    img = PILImage.new("RGB", (640, 480), color=(10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_upload_creates_correct_layout(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path / "store")
    vrepo = FilesystemVehicleRepository(backend)
    rrepo = FilesystemRepairRepository(backend)
    irepo = FilesystemImageRepository(backend)

    vrepo.save(
        Vehicle(
            id=VehicleId("12345"),
            vin="W",
            description="x",
            created_at=datetime(2026, 5, 3, tzinfo=UTC),
        )
    )
    from datetime import date as _date
    from ulid import ULID as _ULID

    repair = Repair(
        id=_ULID(),
        vehicle_id=VehicleId("12345"),
        date=_date(2026, 5, 3),
        description="brakes",
        created_at=datetime(2026, 5, 3, tzinfo=UTC),
    )
    rrepo.save(repair)

    use_case = UploadImageUseCase(rrepo, irepo, PillowImageProcessor())
    image = use_case.execute(
        repair_id=repair.id,
        raw_bytes=_real_jpeg_bytes(),
        filename="my-photo.jpg",
    )

    # Verify filesystem layout per PLAN.md §6.
    repair_dir = tmp_path / "store" / "12345" / "2026-05-03__brakes"
    assert repair_dir.is_dir()
    image_files = sorted(p.name for p in repair_dir.iterdir() if p.is_file())
    assert any(name.startswith("0001_") and name.endswith(".jpg") for name in image_files)
    thumb_dir = repair_dir / "_thumbs"
    assert thumb_dir.is_dir()
    thumbs = list(thumb_dir.iterdir())
    assert len(thumbs) == 1
    # The returned image's storage_key matches the actual key.
    assert backend.exists(image.storage_key)
    assert image.thumbnail_key is not None
    assert backend.exists(image.thumbnail_key)
```

- [ ] **Step 3: Verify failing**

- [ ] **Step 4: Implementation**

`src/edelrep/application/upload_image.py`:

```python
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ulid import ULID

from edelrep.domain.entities import Image, ImageSource
from edelrep.domain.ports import ImageRepository, RepairRepository


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    rotated_bytes: bytes
    thumbnail_bytes: bytes
    captured_at: datetime | None
    mime_type: str


class ImageProcessor(Protocol):
    def process(self, raw_bytes: bytes) -> ProcessedImage: ...


class UploadImageUseCase:
    """Persist a new image: validate repair → process bytes → store entity + bytes."""

    def __init__(
        self,
        repair_repo: RepairRepository,
        image_repo: ImageRepository,
        processor: ImageProcessor,
    ) -> None:
        self._repair_repo = repair_repo
        self._image_repo = image_repo
        self._processor = processor

    def execute(
        self,
        *,
        repair_id: ULID,
        raw_bytes: bytes,
        filename: str,
        source: ImageSource = ImageSource.MANUAL,
    ) -> Image:
        # Raises RepairNotFound if the repair doesn't exist.
        self._repair_repo.get(repair_id)

        processed = self._processor.process(raw_bytes)

        image = Image(
            id=ULID(),
            repair_id=repair_id,
            storage_key="",  # populated by the repository on save/get
            thumbnail_key=None,
            filename=filename,
            mime_type=processed.mime_type,
            size_bytes=len(processed.rotated_bytes),
            source=source,
            uploaded_at=datetime.now(UTC),
            captured_at=processed.captured_at,
        )

        self._image_repo.save(
            image,
            raw_bytes=processed.rotated_bytes,
            thumbnail_bytes=processed.thumbnail_bytes,
        )
        return self._image_repo.get(image.id)
```

- [ ] **Step 5: Tests pass**

- [ ] **Step 6: Gates clean**

- [ ] **Step 7: Commit**

```bash
git add src/edelrep/application/upload_image.py \
        tests/application/test_upload_image.py \
        tests/application/test_upload_image_integration.py
git commit -m "feat(application): add UploadImageUseCase with ImageProcessor port"
```

---

## Task 10: Application package re-exports

**Files:** `src/edelrep/application/__init__.py`

- [ ] **Step 1: Re-export**

```python
from edelrep.application.get_image import GetImageUseCase
from edelrep.application.list_repairs import ListRepairsUseCase
from edelrep.application.search_vehicle import SearchVehicleUseCase
from edelrep.application.upload_image import (
    ImageProcessor,
    ProcessedImage,
    UploadImageUseCase,
)

__all__ = [
    "GetImageUseCase",
    "ImageProcessor",
    "ListRepairsUseCase",
    "ProcessedImage",
    "SearchVehicleUseCase",
    "UploadImageUseCase",
]
```

- [ ] **Step 2: Gates clean**

- [ ] **Step 3: Commit**

```bash
git add src/edelrep/application/__init__.py
git commit -m "feat(application): re-export use cases and processor types"
```

---

## Task 11: Phase 4 acceptance + tag

- [ ] **Step 1: Pyright clean**

- [ ] **Step 2: Pytest with coverage**

```bash
uv run pytest --cov=edelrep --cov-report=term-missing
```

- All tests pass (~250+ expected).
- Total coverage ≥ 95%.
- Every new application/ and infrastructure/exif/ + infrastructure/search/ file ≥ 90%.

- [ ] **Step 3: Ruff clean**

- [ ] **Step 4: Domain framework-import guard**

```bash
! grep -REn "fastapi|sqlalchemy|fsspec|pydantic|httpx|requests|PIL|pillow" src/edelrep/domain/
```

(Added Pillow check.)

- [ ] **Step 5: Application framework-import guard**

```bash
! grep -REn "fastapi|sqlalchemy|fsspec|httpx|requests|PIL|pillow" src/edelrep/application/
```

The application layer only depends on domain ports + stdlib. Pillow lives in `infrastructure/exif/`.

- [ ] **Step 6: Use case integration smoke**

```bash
uv run python -c "
from datetime import UTC, datetime, date
from io import BytesIO
from pathlib import Path
import tempfile

from PIL import Image as PILImage
from ulid import ULID

from edelrep.application import UploadImageUseCase, ListRepairsUseCase, SearchVehicleUseCase, GetImageUseCase
from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.exif.pillow_processor import PillowImageProcessor
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository, FilesystemRepairRepository, FilesystemVehicleRepository,
)
from edelrep.infrastructure.search.in_memory import InMemorySearchIndex
from edelrep.infrastructure.storage import LocalFilesystemBackend

with tempfile.TemporaryDirectory() as td:
    backend = LocalFilesystemBackend(Path(td))
    vrepo = FilesystemVehicleRepository(backend)
    rrepo = FilesystemRepairRepository(backend)
    irepo = FilesystemImageRepository(backend)
    sidx = InMemorySearchIndex()

    v = Vehicle(id=VehicleId('99999'), vin='SMOKE', description=None, created_at=datetime.now(UTC))
    vrepo.save(v); sidx.upsert_vehicle(v)
    r = Repair(id=ULID(), vehicle_id=v.id, date=date.today(), description='smoke',
               created_at=datetime.now(UTC))
    rrepo.save(r)

    img = PILImage.new('RGB', (200, 100), color=(0, 100, 200))
    buf = BytesIO(); img.save(buf, format='JPEG'); raw = buf.getvalue()

    up = UploadImageUseCase(rrepo, irepo, PillowImageProcessor())
    persisted = up.execute(repair_id=r.id, raw_bytes=raw, filename='smoke.jpg')
    print('uploaded', persisted.size_bytes, 'bytes →', persisted.storage_key)

    listed = ListRepairsUseCase(vrepo, rrepo).execute(v.id)
    print('repairs', len(listed))

    found = SearchVehicleUseCase(sidx).execute('SMOKE')
    print('search hits', len(found))

    got, raw_back = GetImageUseCase(irepo, backend).execute(persisted.id)
    print('downloaded', len(raw_back), 'bytes')
    print('OK end-to-end')
"
```

Expected to end with `OK end-to-end`.

- [ ] **Step 7: Tag**

```bash
git tag phase-4-complete
git tag -l
```

Confirm all four tags listed.

- [ ] **Step 8: Final commit if status dirty (typically clean)**

---

## Self-Review Notes

- **Spec coverage:** All four use cases ✅; Pillow EXIF rotation + thumbnail ✅; in-memory SearchIndex ✅; tests use port fakes ✅; integration test verifies on-disk layout ✅.
- **Out of scope for Phase 4:** SQLite SearchIndex (Phase 5), file watcher (Phase 6), web UI (Phase 7), email ingestion (Phase 8), DTO response models, capture-time timezone correction (V1 = UTC).
- **Open follow-ups:** `Image` entity gains `width`/`height` fields in a future phase if the UI needs them. Sidecar history (`schema_version` migration path) is Phase 9. The application-layer `ImageProcessor` Protocol may eventually move to `domain/ports/` if other use cases need it.
