# Phase 1 — Skeleton & Domain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the project skeleton and a fully-typed, framework-free domain layer (entities, value objects, exceptions, ports) with property-based tests for invariants.

**Architecture:** Clean Architecture / Hexagonal. The `domain/` package depends on nothing but the standard library and `python-ulid`. All I/O collaborators are expressed as `typing.Protocol` ports. Filesystem is the eventual source of truth (per PLAN.md §3); this phase only models the contracts.

**Tech Stack:** Python 3.13, uv (dependency manager), ruff (lint+format, line-length 110), pyright (type checker, replacing PLAN.md's mypy), pytest, pytest-cov, hypothesis, python-ulid.

**Deviations from PLAN.md (intentional):**
- Package is `edelrep` (matches `pyproject.toml`), not `fahrzeugbilder`.
- Type checker is pyright (already configured in `pyrightconfig.json`), not mypy.
- `ruff.toml` ignores `N818` so domain exceptions can use DDD-style names (`InvalidVehicleId`, `VehicleNotFound`, etc.) without an `Error` suffix.

**Definition of Done (PLAN.md §12 Phase 1):**
- `uv run pyright` is green.
- `uv run pytest` is green.
- Zero framework imports in `src/edelrep/domain/` (no FastAPI, SQLAlchemy, fsspec, Pydantic).

---

## File Structure

**Created in this phase:**

```
src/edelrep/
├── __init__.py                         # version export
├── domain/
│   ├── __init__.py                     # re-exports Vehicle, Repair, Image, exceptions
│   ├── value_objects.py                # VehicleId (regex-validated)
│   ├── entities.py                     # Vehicle, Repair, Image, ImageSource
│   ├── exceptions.py                   # DomainError + subclasses
│   └── ports/
│       ├── __init__.py
│       ├── vehicle_repository.py       # Protocol for vehicle persistence
│       ├── repair_repository.py        # Protocol for repair persistence
│       ├── image_repository.py         # Protocol for image persistence
│       ├── storage_backend.py          # Protocol for raw bytes/path operations
│       ├── search_index.py             # Protocol for search/index cache
│       └── email_inbox.py              # Protocol for incoming email
tests/
├── __init__.py
└── domain/
    ├── __init__.py
    ├── test_vehicle_id.py              # property-based + boundary tests
    ├── test_entities.py                # entity construction + invariants
    ├── test_exceptions.py              # exception hierarchy
    └── ports/
        ├── __init__.py
        └── test_protocol_compliance.py # in-memory fakes satisfy each Protocol
```

**Modified:**
- `pyproject.toml` — add runtime + dev dependencies; configure pytest.
- `ruff.toml` — already configured (line-length 110); no changes.
- `pyrightconfig.json` — add `src` to include; verify `tests` already there.

**Deleted:**
- `main.py` (uv-init template) — replaced by package layout. The Phase 9 deployment tasks will introduce a real CLI entry point.

---

## Design Notes

### Ports Strategy
Each port is a `typing.Protocol` (structural typing, no inheritance required). For Phase 1 we ship **only the protocols and test that an in-memory fake satisfies each protocol** at type-check time. Real adapters arrive in Phase 2 (filesystem) and Phase 5 (SQLite).

### Identity
- **VehicleId** wraps `registration_number` (Stammnummer). Regex `^[A-Za-z0-9._-]{1,64}$`, frozen dataclass — usable as dict key.
- **Repair.id** and **Image.id** are `ulid.ULID` from `python-ulid` (sortable, time-based). Domain code accepts `ULID` instances; serialization to/from string is an infrastructure concern.

### Exceptions
- Single base `DomainError(Exception)`. Subclasses are flat (no deep hierarchies). Each carries the offending identifier as an attribute, not just a string message — easier for handlers to react.

### Datetimes
- All `created_at`, `uploaded_at`, `captured_at` are `datetime` with **timezone-aware** instances. Naive datetimes are rejected at entity construction.

---

## Task 1: Update dependencies and project metadata

**Files:**
- Modify: `pyproject.toml`
- Modify: `pyrightconfig.json`

- [ ] **Step 1: Add dependencies and pytest config**

Replace `pyproject.toml` with:

```toml
[project]
name = "edelrep"
version = "0.1.0"
description = "Vehicle image and repair management — filesystem-first, locally hosted."
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "python-ulid>=3.0.0",
]

[dependency-groups]
dev = [
    "ruff>=0.8.0",
    "pyright>=1.1.390",
    "pytest>=8.0.0",
    "pytest-cov>=5.0.0",
    "hypothesis>=6.100.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers --strict-config"
xfail_strict = true

[tool.coverage.run]
source = ["src/edelrep"]
branch = true

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/edelrep"]
```

- [ ] **Step 2: Update pyright include paths**

Edit `pyrightconfig.json`, set the `"include"` array to:

```json
"include": ["src", "tests"],
```

(Drop the legacy `"edelrep"` entry — package now lives under `src/edelrep`.)

- [ ] **Step 3: Sync dependencies**

Run: `uv sync`
Expected: `Resolved N packages` and venv populated; `python-ulid`, `pytest`, `hypothesis` listed.

- [ ] **Step 4: Verify pytest can collect (no tests yet)**

Run: `uv run pytest`
Expected: exit code 5 (`no tests ran`) — config is valid, no collection errors.

- [ ] **Step 5: Remove the uv-init template main.py**

Run: `rm /home/elyo/workspace/edelrep/main.py`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml pyrightconfig.json uv.lock
git rm main.py
git commit -m "chore: configure dev deps, pytest, and src layout for edelrep package"
```

---

## Task 2: Create empty package skeleton

**Files:**
- Create: `src/edelrep/__init__.py`
- Create: `src/edelrep/domain/__init__.py`
- Create: `src/edelrep/domain/ports/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/domain/__init__.py`
- Create: `tests/domain/ports/__init__.py`

- [ ] **Step 1: Create `src/edelrep/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 2: Create empty package init files**

Each of these gets a single empty line (no content) — they exist purely to mark packages:

- `src/edelrep/domain/__init__.py`
- `src/edelrep/domain/ports/__init__.py`
- `tests/__init__.py`
- `tests/domain/__init__.py`
- `tests/domain/ports/__init__.py`

- [ ] **Step 3: Verify pyright sees the package**

Run: `uv run pyright src/edelrep`
Expected: `0 errors, 0 warnings, 0 informations`.

- [ ] **Step 4: Commit**

```bash
git add src tests
git commit -m "feat: scaffold edelrep package and tests directories"
```

---

## Task 3: VehicleId value object (TDD)

**Files:**
- Create: `tests/domain/test_vehicle_id.py`
- Create: `src/edelrep/domain/value_objects.py`

- [ ] **Step 1: Write failing tests for VehicleId**

Create `tests/domain/test_vehicle_id.py`:

```python
import re

import pytest
from hypothesis import given, strategies as st

from edelrep.domain.exceptions import InvalidVehicleId
from edelrep.domain.value_objects import VehicleId

VALID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def test_accepts_simple_numeric_registration() -> None:
    vid = VehicleId("12345")
    assert vid.registration_number == "12345"


def test_accepts_max_length() -> None:
    value = "a" * 64
    assert VehicleId(value).registration_number == value


@pytest.mark.parametrize(
    "bad_value",
    ["", "a" * 65, "with space", "umlaut-ü", "slash/here", "123!", "tab\there"],
)
def test_rejects_invalid_strings(bad_value: str) -> None:
    with pytest.raises(InvalidVehicleId) as info:
        VehicleId(bad_value)
    assert info.value.value == bad_value


def test_is_frozen() -> None:
    vid = VehicleId("12345")
    with pytest.raises(AttributeError):
        vid.registration_number = "67890"  # type: ignore[misc]


def test_is_hashable_and_equal_by_value() -> None:
    a = VehicleId("12345")
    b = VehicleId("12345")
    assert a == b
    assert hash(a) == hash(b)
    assert {a, b} == {a}


@given(st.from_regex(VALID_PATTERN, fullmatch=True))
def test_property_valid_inputs_round_trip(value: str) -> None:
    assert VehicleId(value).registration_number == value


@given(st.text(min_size=0, max_size=80))
def test_property_only_pattern_matches_succeed(value: str) -> None:
    if VALID_PATTERN.fullmatch(value):
        VehicleId(value)
    else:
        with pytest.raises(InvalidVehicleId):
            VehicleId(value)
```

- [ ] **Step 2: Run test — verify it fails**

Run: `uv run pytest tests/domain/test_vehicle_id.py -v`
Expected: ImportError / ModuleNotFoundError on `edelrep.domain.value_objects` and `edelrep.domain.exceptions`.

- [ ] **Step 3: Add minimal exception (will be expanded in Task 4)**

Create `src/edelrep/domain/exceptions.py`:

```python
class DomainError(Exception):
    """Base class for all domain-level errors."""


class InvalidVehicleId(DomainError):
    """Raised when a registration number does not match the allowed pattern."""

    def __init__(self, value: str) -> None:
        super().__init__(f"Invalid vehicle registration number: {value!r}")
        self.value = value
```

- [ ] **Step 4: Implement VehicleId**

Create `src/edelrep/domain/value_objects.py`:

```python
import re
from dataclasses import dataclass

from edelrep.domain.exceptions import InvalidVehicleId

_REGISTRATION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@dataclass(frozen=True, slots=True)
class VehicleId:
    """Permanent Swiss vehicle registration number (Stammnummer)."""

    registration_number: str

    def __post_init__(self) -> None:
        if not _REGISTRATION_PATTERN.fullmatch(self.registration_number):
            raise InvalidVehicleId(self.registration_number)
```

- [ ] **Step 5: Run tests — verify they pass**

Run: `uv run pytest tests/domain/test_vehicle_id.py -v`
Expected: all tests pass, including the two hypothesis property tests.

- [ ] **Step 6: Run pyright**

Run: `uv run pyright src/edelrep tests/domain/test_vehicle_id.py`
Expected: `0 errors`.

- [ ] **Step 7: Commit**

```bash
git add src/edelrep/domain/value_objects.py src/edelrep/domain/exceptions.py tests/domain/test_vehicle_id.py
git commit -m "feat(domain): add VehicleId value object with regex validation"
```

---

## Task 4: Expand domain exceptions (TDD)

**Files:**
- Create: `tests/domain/test_exceptions.py`
- Modify: `src/edelrep/domain/exceptions.py`

- [ ] **Step 1: Write failing test**

Create `tests/domain/test_exceptions.py`:

```python
import pytest

from edelrep.domain.exceptions import (
    DomainError,
    DuplicateVehicle,
    ImageNotFound,
    InvalidVehicleId,
    RepairNotFound,
    VehicleNotFound,
)


@pytest.mark.parametrize(
    "exc_cls",
    [InvalidVehicleId, VehicleNotFound, RepairNotFound, ImageNotFound, DuplicateVehicle],
)
def test_all_inherit_from_domain_error(exc_cls: type[Exception]) -> None:
    assert issubclass(exc_cls, DomainError)


def test_vehicle_not_found_carries_id() -> None:
    err = VehicleNotFound("12345")
    assert err.registration_number == "12345"
    assert "12345" in str(err)


def test_repair_not_found_carries_id() -> None:
    err = RepairNotFound("01J9TGZP6X2K0V3W7Y8Z4QABCD")
    assert err.repair_id == "01J9TGZP6X2K0V3W7Y8Z4QABCD"


def test_image_not_found_carries_id() -> None:
    err = ImageNotFound("01J9TGZP6X2K0V3W7Y8Z4QIMAGE")
    assert err.image_id == "01J9TGZP6X2K0V3W7Y8Z4QIMAGE"


def test_duplicate_vehicle_carries_id() -> None:
    err = DuplicateVehicle("12345")
    assert err.registration_number == "12345"
```

- [ ] **Step 2: Run test — verify it fails**

Run: `uv run pytest tests/domain/test_exceptions.py -v`
Expected: ImportError on missing exception classes.

- [ ] **Step 3: Extend exceptions module**

Replace `src/edelrep/domain/exceptions.py` with:

```python
class DomainError(Exception):
    """Base class for all domain-level errors."""


class InvalidVehicleId(DomainError):
    """Raised when a registration number does not match the allowed pattern."""

    def __init__(self, value: str) -> None:
        super().__init__(f"Invalid vehicle registration number: {value!r}")
        self.value = value


class VehicleNotFound(DomainError):
    """Raised when a vehicle lookup misses."""

    def __init__(self, registration_number: str) -> None:
        super().__init__(f"Vehicle not found: {registration_number!r}")
        self.registration_number = registration_number


class DuplicateVehicle(DomainError):
    """Raised when creating a vehicle that already exists."""

    def __init__(self, registration_number: str) -> None:
        super().__init__(f"Vehicle already exists: {registration_number!r}")
        self.registration_number = registration_number


class RepairNotFound(DomainError):
    """Raised when a repair lookup misses."""

    def __init__(self, repair_id: str) -> None:
        super().__init__(f"Repair not found: {repair_id!r}")
        self.repair_id = repair_id


class ImageNotFound(DomainError):
    """Raised when an image lookup misses."""

    def __init__(self, image_id: str) -> None:
        super().__init__(f"Image not found: {image_id!r}")
        self.image_id = image_id
```

- [ ] **Step 4: Run tests — verify pass**

Run: `uv run pytest tests/domain -v`
Expected: all tests pass (Tasks 3 + 4 combined).

- [ ] **Step 5: Pyright check**

Run: `uv run pyright src/edelrep tests/domain`
Expected: `0 errors`.

- [ ] **Step 6: Commit**

```bash
git add src/edelrep/domain/exceptions.py tests/domain/test_exceptions.py
git commit -m "feat(domain): expand exception hierarchy for not-found and duplicate cases"
```

---

## Task 5: Entities — Vehicle, Repair, Image, ImageSource (TDD)

**Files:**
- Create: `tests/domain/test_entities.py`
- Create: `src/edelrep/domain/entities.py`

- [ ] **Step 1: Write failing tests**

Create `tests/domain/test_entities.py`:

```python
from datetime import UTC, date, datetime, timezone

import pytest
from ulid import ULID

from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
from edelrep.domain.value_objects import VehicleId


def _vid() -> VehicleId:
    return VehicleId("12345")


def _now() -> datetime:
    return datetime(2026, 5, 2, 10, 0, tzinfo=UTC)


def test_image_source_values() -> None:
    assert ImageSource.MANUAL.value == "manual"
    assert ImageSource.EMAIL.value == "email"
    assert ImageSource("manual") is ImageSource.MANUAL


def test_vehicle_construction_with_optional_fields() -> None:
    v = Vehicle(id=_vid(), vin="WDB123", description="Kran", created_at=_now())
    assert v.id == _vid()
    assert v.vin == "WDB123"


def test_vehicle_allows_none_vin_and_description() -> None:
    v = Vehicle(id=_vid(), vin=None, description=None, created_at=_now())
    assert v.vin is None
    assert v.description is None


def test_vehicle_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Vehicle(id=_vid(), vin=None, description=None, created_at=datetime(2026, 5, 2, 10, 0))


def test_repair_construction() -> None:
    rid = ULID()
    r = Repair(
        id=rid,
        vehicle_id=_vid(),
        date=date(2026, 4, 15),
        description="Brake pads",
        created_at=_now(),
    )
    assert r.id is rid
    assert r.vehicle_id == _vid()
    assert r.date == date(2026, 4, 15)


def test_repair_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Repair(
            id=ULID(),
            vehicle_id=_vid(),
            date=date(2026, 4, 15),
            description="x",
            created_at=datetime(2026, 5, 2, 10, 0),
        )


def test_image_full_construction() -> None:
    rid = ULID()
    iid = ULID()
    captured = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)
    img = Image(
        id=iid,
        repair_id=rid,
        storage_key="12345/2026-04-15__brakes/0001_<ulid>.jpg",
        thumbnail_key="12345/2026-04-15__brakes/_thumbs/0001_<ulid>.jpg",
        filename="0001_<ulid>.jpg",
        mime_type="image/jpeg",
        size_bytes=4096,
        source=ImageSource.MANUAL,
        uploaded_at=_now(),
        captured_at=captured,
    )
    assert img.id is iid
    assert img.repair_id is rid
    assert img.captured_at == captured


def test_image_allows_optional_thumbnail_and_capture() -> None:
    img = Image(
        id=ULID(),
        repair_id=ULID(),
        storage_key="k",
        thumbnail_key=None,
        filename="x.jpg",
        mime_type="image/jpeg",
        size_bytes=1,
        source=ImageSource.EMAIL,
        uploaded_at=_now(),
        captured_at=None,
    )
    assert img.thumbnail_key is None
    assert img.captured_at is None


def test_image_rejects_naive_uploaded_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Image(
            id=ULID(),
            repair_id=ULID(),
            storage_key="k",
            thumbnail_key=None,
            filename="x.jpg",
            mime_type="image/jpeg",
            size_bytes=1,
            source=ImageSource.MANUAL,
            uploaded_at=datetime(2026, 5, 2, 10, 0),
            captured_at=None,
        )


def test_image_rejects_naive_captured_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Image(
            id=ULID(),
            repair_id=ULID(),
            storage_key="k",
            thumbnail_key=None,
            filename="x.jpg",
            mime_type="image/jpeg",
            size_bytes=1,
            source=ImageSource.MANUAL,
            uploaded_at=_now(),
            captured_at=datetime(2026, 4, 15, 12, 0),
        )


def test_image_rejects_negative_size() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        Image(
            id=ULID(),
            repair_id=ULID(),
            storage_key="k",
            thumbnail_key=None,
            filename="x.jpg",
            mime_type="image/jpeg",
            size_bytes=-1,
            source=ImageSource.MANUAL,
            uploaded_at=_now(),
            captured_at=None,
        )
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `uv run pytest tests/domain/test_entities.py -v`
Expected: ModuleNotFoundError on `edelrep.domain.entities`.

- [ ] **Step 3: Implement entities**

Create `src/edelrep/domain/entities.py`:

```python
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from ulid import ULID

from edelrep.domain.value_objects import VehicleId


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field} must be timezone-aware")


class ImageSource(StrEnum):
    MANUAL = "manual"
    EMAIL = "email"


@dataclass(frozen=True, slots=True)
class Vehicle:
    id: VehicleId
    vin: str | None
    description: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class Repair:
    id: ULID
    vehicle_id: VehicleId
    date: date
    description: str
    created_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class Image:
    id: ULID
    repair_id: ULID
    storage_key: str
    thumbnail_key: str | None
    filename: str
    mime_type: str
    size_bytes: int
    source: ImageSource
    uploaded_at: datetime
    captured_at: datetime | None

    def __post_init__(self) -> None:
        _require_aware(self.uploaded_at, "uploaded_at")
        if self.captured_at is not None:
            _require_aware(self.captured_at, "captured_at")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
```

- [ ] **Step 4: Update domain `__init__.py` to re-export the public API**

Replace `src/edelrep/domain/__init__.py` with:

```python
from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
from edelrep.domain.exceptions import (
    DomainError,
    DuplicateVehicle,
    ImageNotFound,
    InvalidVehicleId,
    RepairNotFound,
    VehicleNotFound,
)
from edelrep.domain.value_objects import VehicleId

__all__ = [
    "DomainError",
    "DuplicateVehicle",
    "Image",
    "ImageNotFound",
    "ImageSource",
    "InvalidVehicleId",
    "Repair",
    "RepairNotFound",
    "Vehicle",
    "VehicleId",
    "VehicleNotFound",
]
```

- [ ] **Step 5: Run tests — verify pass**

Run: `uv run pytest tests/domain -v`
Expected: all entity, vehicle-id, exception tests pass.

- [ ] **Step 6: Pyright check**

Run: `uv run pyright src/edelrep tests/domain`
Expected: `0 errors`.

- [ ] **Step 7: Commit**

```bash
git add src/edelrep/domain/entities.py src/edelrep/domain/__init__.py tests/domain/test_entities.py
git commit -m "feat(domain): add Vehicle, Repair, Image entities and ImageSource enum"
```

---

## Task 6: VehicleRepository port

**Files:**
- Create: `src/edelrep/domain/ports/vehicle_repository.py`

- [ ] **Step 1: Define the protocol**

Create `src/edelrep/domain/ports/vehicle_repository.py`:

```python
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from edelrep.domain.entities import Vehicle
from edelrep.domain.value_objects import VehicleId


@runtime_checkable
class VehicleRepository(Protocol):
    """Persistence port for :class:`Vehicle` aggregates.

    Concrete implementations live in ``edelrep.infrastructure``.
    """

    def get(self, vehicle_id: VehicleId) -> Vehicle:
        """Return the vehicle or raise :class:`VehicleNotFound`."""

    def save(self, vehicle: Vehicle) -> None:
        """Insert a new vehicle. Raises :class:`DuplicateVehicle` on collision."""

    def update(self, vehicle: Vehicle) -> None:
        """Update an existing vehicle. Raises :class:`VehicleNotFound` if absent."""

    def list_all(self) -> Iterable[Vehicle]:
        """Iterate over all known vehicles in unspecified order."""

    def exists(self, vehicle_id: VehicleId) -> bool:
        """Return whether a vehicle with this id is stored."""
```

- [ ] **Step 2: Pyright check**

Run: `uv run pyright src/edelrep/domain/ports/vehicle_repository.py`
Expected: `0 errors`.

- [ ] **Step 3: Commit**

```bash
git add src/edelrep/domain/ports/vehicle_repository.py
git commit -m "feat(domain): add VehicleRepository port"
```

---

## Task 7: RepairRepository port

**Files:**
- Create: `src/edelrep/domain/ports/repair_repository.py`

- [ ] **Step 1: Define the protocol**

Create `src/edelrep/domain/ports/repair_repository.py`:

```python
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from ulid import ULID

from edelrep.domain.entities import Repair
from edelrep.domain.value_objects import VehicleId


@runtime_checkable
class RepairRepository(Protocol):
    """Persistence port for :class:`Repair` aggregates."""

    def get(self, repair_id: ULID) -> Repair:
        """Return the repair or raise :class:`RepairNotFound`."""

    def save(self, repair: Repair) -> None:
        """Insert a new repair record."""

    def update(self, repair: Repair) -> None:
        """Update an existing repair. Raises :class:`RepairNotFound` if absent."""

    def list_for_vehicle(self, vehicle_id: VehicleId) -> Iterable[Repair]:
        """Iterate the vehicle's repairs, newest first."""
```

- [ ] **Step 2: Pyright check**

Run: `uv run pyright src/edelrep/domain/ports/repair_repository.py`
Expected: `0 errors`.

- [ ] **Step 3: Commit**

```bash
git add src/edelrep/domain/ports/repair_repository.py
git commit -m "feat(domain): add RepairRepository port"
```

---

## Task 8: ImageRepository port

**Files:**
- Create: `src/edelrep/domain/ports/image_repository.py`

- [ ] **Step 1: Define the protocol**

Create `src/edelrep/domain/ports/image_repository.py`:

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

    def save(self, image: Image) -> None:
        """Insert a new image record."""

    def list_for_repair(self, repair_id: ULID) -> Iterable[Image]:
        """Iterate the repair's images in upload order."""
```

- [ ] **Step 2: Pyright check**

Run: `uv run pyright src/edelrep/domain/ports/image_repository.py`
Expected: `0 errors`.

- [ ] **Step 3: Commit**

```bash
git add src/edelrep/domain/ports/image_repository.py
git commit -m "feat(domain): add ImageRepository port"
```

---

## Task 9: StorageBackend port

**Files:**
- Create: `src/edelrep/domain/ports/storage_backend.py`

- [ ] **Step 1: Define the protocol**

Create `src/edelrep/domain/ports/storage_backend.py`:

```python
from collections.abc import Iterable
from typing import BinaryIO, Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Low-level byte-stream and path operations for the storage root.

    Implementations may target the local filesystem, S3, WebDAV, etc.
    All paths are POSIX-style strings relative to a storage root.
    """

    def read_bytes(self, key: str) -> bytes:
        """Return the full contents of ``key``. Raises ``FileNotFoundError``."""

    def write_bytes(self, key: str, data: bytes) -> None:
        """Atomically write ``data`` to ``key``, creating parent dirs as needed."""

    def open_read(self, key: str) -> BinaryIO:
        """Open ``key`` for streaming reads. Caller closes the returned object."""

    def delete(self, key: str) -> None:
        """Delete ``key``. No-op if missing."""

    def exists(self, key: str) -> bool:
        """Return whether ``key`` is present."""

    def list_prefix(self, prefix: str) -> Iterable[str]:
        """Iterate keys whose path starts with ``prefix``."""
```

- [ ] **Step 2: Pyright check**

Run: `uv run pyright src/edelrep/domain/ports/storage_backend.py`
Expected: `0 errors`.

- [ ] **Step 3: Commit**

```bash
git add src/edelrep/domain/ports/storage_backend.py
git commit -m "feat(domain): add StorageBackend port"
```

---

## Task 10: SearchIndex port

**Files:**
- Create: `src/edelrep/domain/ports/search_index.py`

- [ ] **Step 1: Define the protocol**

Create `src/edelrep/domain/ports/search_index.py`:

```python
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from edelrep.domain.entities import Vehicle
from edelrep.domain.value_objects import VehicleId


@runtime_checkable
class SearchIndex(Protocol):
    """Read/write port for the (rebuildable) index cache.

    The index is never the source of truth — it must be reproducible from
    the filesystem. Mutating methods are idempotent.
    """

    def search_vehicles(self, query: str, limit: int = 20) -> Iterable[Vehicle]:
        """Full-text search over registration_number, vin, description."""

    def upsert_vehicle(self, vehicle: Vehicle) -> None:
        """Insert or update the index row for ``vehicle``."""

    def remove_vehicle(self, vehicle_id: VehicleId) -> None:
        """Drop the index row. No-op if absent."""

    def clear(self) -> None:
        """Drop all rows. Used before a full reindex."""
```

- [ ] **Step 2: Pyright check**

Run: `uv run pyright src/edelrep/domain/ports/search_index.py`
Expected: `0 errors`.

- [ ] **Step 3: Commit**

```bash
git add src/edelrep/domain/ports/search_index.py
git commit -m "feat(domain): add SearchIndex port"
```

---

## Task 11: EmailInbox port

**Files:**
- Create: `src/edelrep/domain/ports/email_inbox.py`

- [ ] **Step 1: Define the protocol and a transport DTO**

Create `src/edelrep/domain/ports/email_inbox.py`:

```python
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    filename: str
    mime_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class EmailMessage:
    message_id: str
    from_address: str
    subject: str
    received_at: datetime
    body_text: str
    attachments: Sequence[EmailAttachment]


@runtime_checkable
class EmailInbox(Protocol):
    """Inbound port for an external mail server.

    Implementations must be idempotent: marking a message processed twice
    is allowed and silent.
    """

    def fetch_unread(self, limit: int = 50) -> Iterable[EmailMessage]:
        """Return up to ``limit`` unread messages, oldest first."""

    def mark_processed(self, message_id: str) -> None:
        """Flag a message as handled (e.g., set IMAP ``\\Seen`` and a label)."""
```

- [ ] **Step 2: Pyright check**

Run: `uv run pyright src/edelrep/domain/ports/email_inbox.py`
Expected: `0 errors`.

- [ ] **Step 3: Commit**

```bash
git add src/edelrep/domain/ports/email_inbox.py
git commit -m "feat(domain): add EmailInbox port and message DTOs"
```

---

## Task 12: Ports `__init__` re-exports

**Files:**
- Modify: `src/edelrep/domain/ports/__init__.py`

- [ ] **Step 1: Add re-exports**

Replace `src/edelrep/domain/ports/__init__.py` with:

```python
from edelrep.domain.ports.email_inbox import EmailAttachment, EmailInbox, EmailMessage
from edelrep.domain.ports.image_repository import ImageRepository
from edelrep.domain.ports.repair_repository import RepairRepository
from edelrep.domain.ports.search_index import SearchIndex
from edelrep.domain.ports.storage_backend import StorageBackend
from edelrep.domain.ports.vehicle_repository import VehicleRepository

__all__ = [
    "EmailAttachment",
    "EmailInbox",
    "EmailMessage",
    "ImageRepository",
    "RepairRepository",
    "SearchIndex",
    "StorageBackend",
    "VehicleRepository",
]
```

- [ ] **Step 2: Pyright check**

Run: `uv run pyright src/edelrep`
Expected: `0 errors`.

- [ ] **Step 3: Commit**

```bash
git add src/edelrep/domain/ports/__init__.py
git commit -m "feat(domain): re-export ports from edelrep.domain.ports"
```

---

## Task 13: Protocol-compliance test with in-memory fakes (TDD)

**Purpose:** Prove every Protocol can actually be implemented. Catches signature drift today and gives Phase 4 a head-start on test doubles.

**Files:**
- Create: `tests/domain/ports/test_protocol_compliance.py`

- [ ] **Step 1: Write the test**

Create `tests/domain/ports/test_protocol_compliance.py`:

```python
from collections.abc import Iterable, Sequence
from typing import BinaryIO

from ulid import ULID

from edelrep.domain.entities import Image, Repair, Vehicle
from edelrep.domain.ports import (
    EmailInbox,
    EmailMessage,
    ImageRepository,
    RepairRepository,
    SearchIndex,
    StorageBackend,
    VehicleRepository,
)
from edelrep.domain.value_objects import VehicleId


class _FakeVehicleRepo:
    def __init__(self) -> None:
        self._store: dict[VehicleId, Vehicle] = {}

    def get(self, vehicle_id: VehicleId) -> Vehicle:
        return self._store[vehicle_id]

    def save(self, vehicle: Vehicle) -> None:
        self._store[vehicle.id] = vehicle

    def update(self, vehicle: Vehicle) -> None:
        self._store[vehicle.id] = vehicle

    def list_all(self) -> Iterable[Vehicle]:
        return list(self._store.values())

    def exists(self, vehicle_id: VehicleId) -> bool:
        return vehicle_id in self._store


class _FakeRepairRepo:
    def __init__(self) -> None:
        self._store: dict[ULID, Repair] = {}

    def get(self, repair_id: ULID) -> Repair:
        return self._store[repair_id]

    def save(self, repair: Repair) -> None:
        self._store[repair.id] = repair

    def update(self, repair: Repair) -> None:
        self._store[repair.id] = repair

    def list_for_vehicle(self, vehicle_id: VehicleId) -> Iterable[Repair]:
        return [r for r in self._store.values() if r.vehicle_id == vehicle_id]


class _FakeImageRepo:
    def __init__(self) -> None:
        self._store: dict[ULID, Image] = {}

    def get(self, image_id: ULID) -> Image:
        return self._store[image_id]

    def save(self, image: Image) -> None:
        self._store[image.id] = image

    def list_for_repair(self, repair_id: ULID) -> Iterable[Image]:
        return [i for i in self._store.values() if i.repair_id == repair_id]


class _FakeStorage:
    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    def read_bytes(self, key: str) -> bytes:
        return self._files[key]

    def write_bytes(self, key: str, data: bytes) -> None:
        self._files[key] = data

    def open_read(self, key: str) -> BinaryIO:  # pragma: no cover - structural only
        raise NotImplementedError

    def delete(self, key: str) -> None:
        self._files.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._files

    def list_prefix(self, prefix: str) -> Iterable[str]:
        return [k for k in self._files if k.startswith(prefix)]


class _FakeSearchIndex:
    def __init__(self) -> None:
        self._rows: dict[VehicleId, Vehicle] = {}

    def search_vehicles(self, query: str, limit: int = 20) -> Iterable[Vehicle]:
        return list(self._rows.values())[:limit]

    def upsert_vehicle(self, vehicle: Vehicle) -> None:
        self._rows[vehicle.id] = vehicle

    def remove_vehicle(self, vehicle_id: VehicleId) -> None:
        self._rows.pop(vehicle_id, None)

    def clear(self) -> None:
        self._rows.clear()


class _FakeInbox:
    def __init__(self, messages: Sequence[EmailMessage] = ()) -> None:
        self._messages = list(messages)
        self.processed: list[str] = []

    def fetch_unread(self, limit: int = 50) -> Iterable[EmailMessage]:
        return self._messages[:limit]

    def mark_processed(self, message_id: str) -> None:
        self.processed.append(message_id)


def test_fake_vehicle_repo_satisfies_protocol() -> None:
    repo: VehicleRepository = _FakeVehicleRepo()
    assert isinstance(repo, VehicleRepository)


def test_fake_repair_repo_satisfies_protocol() -> None:
    repo: RepairRepository = _FakeRepairRepo()
    assert isinstance(repo, RepairRepository)


def test_fake_image_repo_satisfies_protocol() -> None:
    repo: ImageRepository = _FakeImageRepo()
    assert isinstance(repo, ImageRepository)


def test_fake_storage_satisfies_protocol() -> None:
    storage: StorageBackend = _FakeStorage()
    assert isinstance(storage, StorageBackend)


def test_fake_search_index_satisfies_protocol() -> None:
    idx: SearchIndex = _FakeSearchIndex()
    assert isinstance(idx, SearchIndex)


def test_fake_inbox_satisfies_protocol() -> None:
    inbox: EmailInbox = _FakeInbox()
    assert isinstance(inbox, EmailInbox)
```

- [ ] **Step 2: Run tests — verify they pass**

Run: `uv run pytest tests/domain/ports -v`
Expected: 6 tests passing.

- [ ] **Step 3: Pyright check**

Run: `uv run pyright tests/domain/ports`
Expected: `0 errors`. The variable annotations (`repo: VehicleRepository = _FakeVehicleRepo()`) prove static structural compatibility.

- [ ] **Step 4: Commit**

```bash
git add tests/domain/ports/test_protocol_compliance.py
git commit -m "test(domain): verify in-memory fakes satisfy every port protocol"
```

---

## Task 14: Phase 1 acceptance — DoD verification

**Files:** none (verification only).

- [ ] **Step 1: Run full pyright**

Run: `uv run pyright`
Expected: `0 errors, 0 warnings`.

- [ ] **Step 2: Run full pytest with coverage**

Run: `uv run pytest --cov=edelrep --cov-report=term-missing`
Expected: all tests pass; domain coverage ≥ 95%.

- [ ] **Step 3: Verify ruff is clean**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: `All checks passed!` and `N files already formatted`.

- [ ] **Step 4: Verify no framework imports leaked into domain**

Run:
```bash
! grep -REn "fastapi|sqlalchemy|fsspec|pydantic|httpx|requests" src/edelrep/domain/
```
Expected: command exits 0 (grep matched nothing — `!` negates exit code).

- [ ] **Step 5: Tag the phase commit**

```bash
git tag phase-1-complete
```

- [ ] **Step 6: Final phase-completion commit (if anything was tweaked)**

If any of the steps above produced changes:
```bash
git add -A
git commit -m "chore: phase 1 acceptance — pyright/pytest/ruff green, no framework leaks"
```

If everything was already clean, skip this step — the tag is enough.

---

## Self-Review Notes

- **Spec coverage (PLAN.md §12 Phase 1):** project skeleton ✅ (Tasks 1-2), entities/value-objects/exceptions ✅ (Tasks 3-5), all six ports as Protocols ✅ (Tasks 6-12), property-based VehicleId tests ✅ (Task 3), pyright green ✅ (Task 14), no framework imports ✅ (Task 14 grep gate).
- **Out of scope:** No filesystem I/O, no SQLite, no FastAPI, no email — all deferred to later phase plans (one document per phase).
- **Naming consistency:** `VehicleId.registration_number`, `Repair.vehicle_id`, `Image.repair_id` align with PLAN.md §7. `ImageSource` values `"manual"`/`"email"` match §11 label-mapping table.
