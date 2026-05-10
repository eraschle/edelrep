# Bild-Kommentare, Repair-Tiebreaker, Fahrzeug-Dropdown — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drei UX-Verbesserungen ausliefern — optionaler Per-Image-Kommentar (Upload + Modal-Edit), stabiler Tiebreaker bei Repair-Sortierung, und volle Fahrzeugliste auf `/search` mit Fuzzy-Filter.

**Architecture:** Per-Image-Sidecar `NNNN_<ulid>.json` ergänzt das FS-Storage. Im SQLite-Index wird Aktivität via `MAX(repair.id, image.id)` (ULID-Lexikographie) abgeleitet; `python-ulid` liefert das `.datetime`-Property. Fuzzy Search läuft server-seitig via `rapidfuzz` über einen neuen `FuzzyMatcher`-Port. Bestehende Clean-Architecture-Schichten bleiben unverändert.

**Tech Stack:** FastAPI, Jinja2, vanilla JS, pytest + FastAPI `TestClient`, `rapidfuzz` (neu), `python-ulid`.

**Spec:** `docs/superpowers/specs/2026-05-10-image-comments-sorting-vehicle-dropdown-design.md`

---

## File Structure

**Neue Dateien:**

- `src/edelrep/domain/ports/fuzzy_matcher.py` — Protocol `FuzzyMatcher` mit `score(query, candidate) -> float` (0..100).
- `src/edelrep/application/update_image_comment.py` — Use-Case `UpdateImageCommentUseCase` mit Validierung und Normalisierung.
- `src/edelrep/infrastructure/search/rapidfuzz_matcher.py` — Adapter `RapidFuzzMatcher` (rapidfuzz `WRatio`).
- `tests/domain/ports/test_fuzzy_matcher.py` — Smoke-Test für Protocol-Konformität.
- `tests/application/test_update_image_comment.py` — Use-Case-Tests.
- `tests/infrastructure/search/test_rapidfuzz_matcher.py` — Score-Smoke-Tests.

**Geänderte Dateien:**

- `pyproject.toml` — `rapidfuzz>=3.10.0` zu `dependencies`.
- `src/edelrep/domain/entities.py` — `Image.comment: str | None = None` plus Längen-Check.
- `src/edelrep/domain/ports/image_repository.py` — neue Methode `update_comment`.
- `src/edelrep/domain/ports/search_index.py` — neue Methode `list_vehicles_by_activity`.
- `src/edelrep/domain/ports/__init__.py` — `FuzzyMatcher` exportieren.
- `src/edelrep/infrastructure/filesystem/layout.py` — `image_sidecar_key`, `is_image_sidecar_key`, Regex.
- `src/edelrep/infrastructure/filesystem/image_store.py` — Sidecar persistieren/lesen, `update_comment`.
- `src/edelrep/infrastructure/filesystem/repair_store.py` — Tiebreaker `(date, created_at)` DESC.
- `src/edelrep/infrastructure/index/sqlite_search_index.py` — `list_vehicles_by_activity`.
- `src/edelrep/infrastructure/watcher/key_mapper.py` — neuer `EntityKind.IMAGE_SIDECAR`, Routing in `classify`.
- `src/edelrep/infrastructure/watcher/event_handler.py` — Sidecar-Kind nicht filtern.
- `src/edelrep/infrastructure/watcher/live_index.py` — `IMAGE_SIDECAR` auf `_handle_image` routen.
- `src/edelrep/application/upload_image.py` — `comment: str | None`-Parameter.
- `src/edelrep/application/search_vehicle.py` — `FuzzyMatcher` injizieren, leerer Query → Activity-Liste.
- `src/edelrep/application/__init__.py` — `UpdateImageCommentUseCase` exportieren.
- `src/edelrep/presentation/container.py` — `RapidFuzzMatcher` + `UpdateImageCommentUseCase` verdrahten.
- `src/edelrep/presentation/routes/images.py` — `comment` Form-Field; neuer `PATCH /images/{id}/comment`.
- `src/edelrep/presentation/routes/search.py` — `GET /search` rendert volle Liste; `is_empty_filter`-Flag an Template.
- `src/edelrep/presentation/templates/_image_picker.html` — Textarea pro Eintrag, `pickerApi` liefert `comment`.
- `src/edelrep/presentation/templates/new_repair.html` — JS sendet `comment` mit hoch.
- `src/edelrep/presentation/templates/upload_image.html` — JS sendet `comment` mit hoch.
- `src/edelrep/presentation/templates/vehicle_detail.html` — Caption + Modal.
- `src/edelrep/presentation/templates/search.html` — Placeholder-Hinweis, Initial-Render zeigt Liste.
- `src/edelrep/presentation/templates/_vehicle_search_results.html` — `is_empty_filter`-Unterscheidung.
- `docs/architecture.md` — Z. 125-Block ersetzen (Image-Sidecar dokumentieren).
- Test-Dateien: `tests/domain/test_entities.py`, `tests/application/test_upload_image.py`, `tests/application/test_search_vehicle.py`, `tests/infrastructure/filesystem/test_image_store.py`, `tests/infrastructure/filesystem/test_repair_store.py` (bzw. äquivalent), `tests/infrastructure/index/test_sqlite_search_index.py`, `tests/infrastructure/watcher/` (Sidecar-Routing), `tests/presentation/test_images.py`, `tests/presentation/test_search.py`.

---

## Task 1: Domain — `FuzzyMatcher`-Port

**Files:**
- Create: `src/edelrep/domain/ports/fuzzy_matcher.py`
- Create: `tests/domain/ports/test_fuzzy_matcher.py`
- Modify: `src/edelrep/domain/ports/__init__.py`

- [ ] **Step 1.1: Failing Test schreiben**

Datei `tests/domain/ports/test_fuzzy_matcher.py` neu anlegen:

```python
from edelrep.domain.ports import FuzzyMatcher


class _DummyMatcher:
    def score(self, query: str, candidate: str) -> float:
        return 100.0 if query == candidate else 0.0


def test_fuzzy_matcher_protocol_runtime_check() -> None:
    matcher: FuzzyMatcher = _DummyMatcher()
    assert isinstance(matcher, FuzzyMatcher)
    assert matcher.score("a", "a") == 100.0
    assert matcher.score("a", "b") == 0.0
```

- [ ] **Step 1.2: Tests ausführen — Fail erwartet**

Run: `uv run pytest tests/domain/ports/test_fuzzy_matcher.py -v`
Expected: `ImportError: cannot import name 'FuzzyMatcher' from 'edelrep.domain.ports'`.

- [ ] **Step 1.3: Port schreiben**

Datei `src/edelrep/domain/ports/fuzzy_matcher.py` neu anlegen:

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class FuzzyMatcher(Protocol):
    """Port for a fuzzy-string-matching engine.

    Implementations return a similarity score in the 0..100 range. The
    domain has no preference for a specific algorithm; the adapter
    chooses (e.g. ``rapidfuzz.fuzz.WRatio``).
    """

    def score(self, query: str, candidate: str) -> float: ...
```

- [ ] **Step 1.4: Port im `__init__.py` exportieren**

`src/edelrep/domain/ports/__init__.py` ersetzen durch:

```python
from edelrep.domain.ports.email_inbox import EmailAttachment, EmailInbox, EmailMessage
from edelrep.domain.ports.fuzzy_matcher import FuzzyMatcher
from edelrep.domain.ports.image_repository import ImageRepository
from edelrep.domain.ports.repair_repository import RepairRepository
from edelrep.domain.ports.search_index import SearchIndex
from edelrep.domain.ports.storage_backend import StorageBackend
from edelrep.domain.ports.vehicle_repository import VehicleRepository

__all__ = [
    "EmailAttachment",
    "EmailInbox",
    "EmailMessage",
    "FuzzyMatcher",
    "ImageRepository",
    "RepairRepository",
    "SearchIndex",
    "StorageBackend",
    "VehicleRepository",
]
```

- [ ] **Step 1.5: Tests ausführen — grün**

Run: `uv run pytest tests/domain/ports/test_fuzzy_matcher.py -v`
Expected: 1 passed.

- [ ] **Step 1.6: Committen**

```bash
git add src/edelrep/domain/ports/fuzzy_matcher.py src/edelrep/domain/ports/__init__.py tests/domain/ports/test_fuzzy_matcher.py
git commit -m "feat(domain): add FuzzyMatcher port for similarity scoring"
```

---

## Task 2: Domain — `Image.comment`-Feld

**Files:**
- Modify: `src/edelrep/domain/entities.py`
- Modify: `tests/domain/test_entities.py`

- [ ] **Step 2.1: Failing Tests schreiben**

In `tests/domain/test_entities.py` am Ende anhängen:

```python
def _aware_now() -> datetime:
    return datetime.now(UTC)


def _build_image(*, comment: str | None = None) -> Image:
    return Image(
        id=ULID(),
        repair_id=ULID(),
        storage_key="",
        thumbnail_key=None,
        filename="x.jpg",
        mime_type="image/jpeg",
        size_bytes=10,
        source=ImageSource.MANUAL,
        uploaded_at=_aware_now(),
        captured_at=None,
        comment=comment,
    )


def test_image_default_comment_is_none() -> None:
    img = _build_image()
    assert img.comment is None


def test_image_accepts_short_comment() -> None:
    img = _build_image(comment="brakes")
    assert img.comment == "brakes"


def test_image_rejects_comment_over_1000_chars() -> None:
    too_long = "x" * 1001
    with pytest.raises(ValueError, match="too long"):
        _build_image(comment=too_long)
```

Sicherstellen, dass die nötigen Imports oben in der Datei stehen (`from datetime import UTC, datetime`, `from ulid import ULID`, `from edelrep.domain.entities import Image, ImageSource`, `import pytest`). Falls Imports fehlen, ergänzen.

- [ ] **Step 2.2: Tests laufen lassen — Fail erwartet**

Run: `uv run pytest tests/domain/test_entities.py -v -k "comment"`
Expected: 3 errors — `Image.__init__()` kennt `comment` nicht.

- [ ] **Step 2.3: Image-Entity erweitern**

In `src/edelrep/domain/entities.py` die `Image`-Dataclass durch folgende ersetzen:

```python
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
    comment: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.uploaded_at, "uploaded_at")
        if self.captured_at is not None:
            _require_aware(self.captured_at, "captured_at")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        if self.comment is not None and len(self.comment) > 1000:
            raise ValueError("comment too long (max 1000 chars)")
```

- [ ] **Step 2.4: Tests grün**

Run: `uv run pytest tests/domain/test_entities.py -v`
Expected: alle bestehenden + 3 neue passen.

- [ ] **Step 2.5: Committen**

```bash
git add src/edelrep/domain/entities.py tests/domain/test_entities.py
git commit -m "feat(domain): add optional comment field to Image entity (max 1000 chars)"
```

---

## Task 3: Domain — Port-Methoden `update_comment` & `list_vehicles_by_activity`

**Files:**
- Modify: `src/edelrep/domain/ports/image_repository.py`
- Modify: `src/edelrep/domain/ports/search_index.py`

Diese Schritte fügen nur Protocol-Methoden hinzu — keine Tests nötig, weil Protocol-Compliance über Adapter-Tests geprüft wird (Tasks 6, 8).

- [ ] **Step 3.1: `ImageRepository`-Port erweitern**

In `src/edelrep/domain/ports/image_repository.py` die Klasse ersetzen durch:

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
        writing both byte streams atomically. If ``image.comment`` is
        non-``None`` the implementation must also persist it."""
        ...

    def list_for_repair(self, repair_id: ULID) -> Iterable[Image]:
        """Iterate the repair's images in upload order."""
        ...

    def update_comment(self, image_id: ULID, comment: str | None) -> None:
        """Set or clear the comment for an existing image.

        ``None`` removes any persisted comment. Raises
        :class:`ImageNotFound` when the image does not exist.
        """
        ...
```

- [ ] **Step 3.2: `SearchIndex`-Port erweitern**

In `src/edelrep/domain/ports/search_index.py` die Klasse ersetzen durch:

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
        ...

    def list_vehicles_by_activity(self, limit: int) -> Iterable[Vehicle]:
        """Iterate vehicles, most-recently-active first.

        Activity is the maximum of (most recent repair, most recent image
        upload, vehicle.created_at). Implementations decide how they
        materialise this ranking.
        """
        ...

    def upsert_vehicle(self, vehicle: Vehicle) -> None:
        """Insert or update the index row for ``vehicle``."""
        ...

    def remove_vehicle(self, vehicle_id: VehicleId) -> None:
        """Drop the index row. No-op if absent."""
        ...

    def clear(self) -> None:
        """Drop all rows. Used before a full reindex."""
        ...
```

- [ ] **Step 3.3: Pyright-Check**

Run: `uv run pyright`
Expected: 0 Errors. (Bestehende Implementierungen erfüllen die Protokolle noch nicht — aber die werden in den nachfolgenden Tasks ergänzt; jeder Task läuft seinen eigenen Lint-Check. Falls Pyright hier auf Implementations-Lücken zeigt, sind die akzeptabel als noch-nicht-implementiert; sie verschwinden in Task 6 und Task 8.)

- [ ] **Step 3.4: Committen**

```bash
git add src/edelrep/domain/ports/image_repository.py src/edelrep/domain/ports/search_index.py
git commit -m "feat(domain): add update_comment and list_vehicles_by_activity port methods"
```

---

## Task 4: Infra — Layout-Helpers für Image-Sidecar

**Files:**
- Modify: `src/edelrep/infrastructure/filesystem/layout.py`
- Modify: `tests/infrastructure/filesystem/test_layout.py` (anlegen falls fehlend)

- [ ] **Step 4.1: Testdatei lokalisieren**

Run: `ls tests/infrastructure/filesystem/`
Falls `test_layout.py` existiert, dort anhängen. Falls nicht: `tests/infrastructure/filesystem/test_layout.py` neu anlegen mit:

```python
from edelrep.domain.value_objects import VehicleId
```

(Header-Imports werden Task-spezifisch in Step 4.2 ergänzt.)

- [ ] **Step 4.2: Failing Tests schreiben**

In `tests/infrastructure/filesystem/test_layout.py` anhängen:

```python
from edelrep.infrastructure.filesystem.layout import (
    image_sidecar_key,
    is_image_sidecar_key,
)


def test_image_sidecar_key_replaces_extension_with_json() -> None:
    vid = VehicleId("12345")
    key = image_sidecar_key(vid, "2026-05-10__brakes", "0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg")
    assert key == "12345/2026-05-10__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.json"


def test_is_image_sidecar_key_accepts_valid() -> None:
    assert is_image_sidecar_key(
        "12345/2026-05-10__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.json"
    )


def test_is_image_sidecar_key_rejects_repair_sidecar() -> None:
    assert not is_image_sidecar_key("12345/2026-05-10__brakes/_repair.json")


def test_is_image_sidecar_key_rejects_image_jpg() -> None:
    assert not is_image_sidecar_key(
        "12345/2026-05-10__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg"
    )
```

- [ ] **Step 4.3: Tests laufen — Fail erwartet**

Run: `uv run pytest tests/infrastructure/filesystem/test_layout.py -v`
Expected: 4 ImportError / NameError.

- [ ] **Step 4.4: Layout erweitern**

In `src/edelrep/infrastructure/filesystem/layout.py` am Ende anhängen:

```python
_IMAGE_SIDECAR_KEY_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}/\d{4}-\d{2}-\d{2}__[a-z0-9-]+"
    r"/\d{4}_[0-9A-HJKMNP-TV-Z]{26}\.json$"
)


def image_sidecar_key(vehicle_id: VehicleId, dir_name: str, image_filename_value: str) -> str:
    stem = image_filename_value.rsplit(".", 1)[0]
    return f"{vehicle_id.registration_number}/{dir_name}/{stem}.json"


def is_image_sidecar_key(key: str) -> bool:
    return bool(_IMAGE_SIDECAR_KEY_RE.match(key))
```

- [ ] **Step 4.5: Tests grün**

Run: `uv run pytest tests/infrastructure/filesystem/test_layout.py -v`
Expected: 4 passed.

- [ ] **Step 4.6: Committen**

```bash
git add src/edelrep/infrastructure/filesystem/layout.py tests/infrastructure/filesystem/test_layout.py
git commit -m "feat(layout): add image_sidecar_key + is_image_sidecar_key helpers"
```

---

## Task 5: Infra — `RapidFuzzMatcher` + Dependency

**Files:**
- Modify: `pyproject.toml`
- Create: `src/edelrep/infrastructure/search/rapidfuzz_matcher.py`
- Create: `tests/infrastructure/search/test_rapidfuzz_matcher.py`

- [ ] **Step 5.1: Dependency ergänzen**

In `pyproject.toml` die `dependencies`-Liste erweitern auf:

```toml
dependencies = [
    "Pillow>=11.0.0",
    "apscheduler>=3.11.0",
    "fastapi>=0.115.0",
    "fsspec>=2024.0.0",
    "imap-tools>=1.10.0",
    "jinja2>=3.1.4",
    "python-multipart>=0.0.20",
    "python-ulid>=3.0.0",
    "rapidfuzz>=3.10.0",
    "uvicorn>=0.32.0",
    "watchdog>=4.0.0",
]
```

- [ ] **Step 5.2: Lock-File aktualisieren**

Run: `uv sync`
Expected: `rapidfuzz` neu im `uv.lock`, kein Test-Run nötig.

- [ ] **Step 5.3: Failing Tests schreiben**

`tests/infrastructure/search/test_rapidfuzz_matcher.py` anlegen:

```python
from edelrep.infrastructure.search.rapidfuzz_matcher import RapidFuzzMatcher


def test_identical_strings_score_100() -> None:
    matcher = RapidFuzzMatcher()
    assert matcher.score("hello", "hello") == 100.0


def test_completely_different_strings_score_low() -> None:
    matcher = RapidFuzzMatcher()
    assert matcher.score("abc", "xyz123") < 30.0


def test_one_char_typo_scores_high() -> None:
    matcher = RapidFuzzMatcher()
    assert matcher.score("Mercedes", "Mercades") >= 80.0


def test_empty_query_returns_zero() -> None:
    matcher = RapidFuzzMatcher()
    assert matcher.score("", "anything") == 0.0


def test_empty_candidate_returns_zero() -> None:
    matcher = RapidFuzzMatcher()
    assert matcher.score("query", "") == 0.0
```

- [ ] **Step 5.4: Tests laufen lassen — Fail erwartet**

Run: `uv run pytest tests/infrastructure/search/test_rapidfuzz_matcher.py -v`
Expected: 5 ModuleNotFoundError.

- [ ] **Step 5.5: Adapter schreiben**

`src/edelrep/infrastructure/search/rapidfuzz_matcher.py` anlegen:

```python
from rapidfuzz import fuzz


class RapidFuzzMatcher:
    """FuzzyMatcher adapter using rapidfuzz's WRatio (0..100)."""

    def score(self, query: str, candidate: str) -> float:
        if not query or not candidate:
            return 0.0
        return float(fuzz.WRatio(query, candidate))
```

- [ ] **Step 5.6: Tests grün**

Run: `uv run pytest tests/infrastructure/search/test_rapidfuzz_matcher.py -v`
Expected: 5 passed.

- [ ] **Step 5.7: Committen**

```bash
git add pyproject.toml uv.lock src/edelrep/infrastructure/search/rapidfuzz_matcher.py tests/infrastructure/search/test_rapidfuzz_matcher.py
git commit -m "feat(search): add RapidFuzzMatcher adapter (WRatio scoring)"
```

---

## Task 6: Infra — Image-Sidecar in `FilesystemImageRepository`

**Files:**
- Modify: `src/edelrep/infrastructure/filesystem/image_store.py`
- Modify: `tests/infrastructure/filesystem/test_image_store.py`

- [ ] **Step 6.1: Failing Tests schreiben**

Existierende Testdatei prüfen mit `cat tests/infrastructure/filesystem/test_image_store.py | head -40`. Anschliessend folgende Tests anhängen (Imports oben anpassen, falls nötig: `from edelrep.infrastructure.filesystem.layout import image_sidecar_key`).

```python
def test_save_persists_comment_in_sidecar(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path)
    vehicle_repo = FilesystemVehicleRepository(backend)
    repair_repo = FilesystemRepairRepository(backend)
    image_repo = FilesystemImageRepository(backend)
    vehicle = _seed_vehicle(vehicle_repo)
    repair = _seed_repair(repair_repo, vehicle.id)

    img = Image(
        id=ULID(),
        repair_id=repair.id,
        storage_key="",
        thumbnail_key=None,
        filename="x.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime.now(UTC),
        captured_at=None,
        comment="brakes left front",
    )
    image_repo.save(img, raw_bytes=b"\x00\x00\x00\x00")

    sidecar_path = tmp_path / "12345" / repair_dir_name(repair.date, repair.description) / f"0001_{img.id!s}.json"
    assert sidecar_path.is_file()


def test_reconstruct_reads_comment_when_sidecar_present(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path)
    vehicle_repo = FilesystemVehicleRepository(backend)
    repair_repo = FilesystemRepairRepository(backend)
    image_repo = FilesystemImageRepository(backend)
    vehicle = _seed_vehicle(vehicle_repo)
    repair = _seed_repair(repair_repo, vehicle.id)

    img = Image(
        id=ULID(), repair_id=repair.id, storage_key="", thumbnail_key=None,
        filename="x.jpg", mime_type="image/jpeg", size_bytes=4,
        source=ImageSource.MANUAL, uploaded_at=datetime.now(UTC), captured_at=None,
        comment="hello world",
    )
    image_repo.save(img, raw_bytes=b"\x00\x00\x00\x00")

    reread = image_repo.get(img.id)
    assert reread.comment == "hello world"


def test_save_without_comment_writes_no_sidecar(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path)
    vehicle_repo = FilesystemVehicleRepository(backend)
    repair_repo = FilesystemRepairRepository(backend)
    image_repo = FilesystemImageRepository(backend)
    vehicle = _seed_vehicle(vehicle_repo)
    repair = _seed_repair(repair_repo, vehicle.id)

    img = Image(
        id=ULID(), repair_id=repair.id, storage_key="", thumbnail_key=None,
        filename="x.jpg", mime_type="image/jpeg", size_bytes=4,
        source=ImageSource.MANUAL, uploaded_at=datetime.now(UTC), captured_at=None,
    )
    image_repo.save(img, raw_bytes=b"\x00\x00\x00\x00")

    expected_dir = tmp_path / "12345" / repair_dir_name(repair.date, repair.description)
    json_files = [p for p in expected_dir.iterdir() if p.suffix == ".json" and p.name != "_repair.json"]
    assert json_files == []


def test_update_comment_writes_sidecar(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path)
    vehicle_repo = FilesystemVehicleRepository(backend)
    repair_repo = FilesystemRepairRepository(backend)
    image_repo = FilesystemImageRepository(backend)
    vehicle = _seed_vehicle(vehicle_repo)
    repair = _seed_repair(repair_repo, vehicle.id)

    img = Image(
        id=ULID(), repair_id=repair.id, storage_key="", thumbnail_key=None,
        filename="x.jpg", mime_type="image/jpeg", size_bytes=4,
        source=ImageSource.MANUAL, uploaded_at=datetime.now(UTC), captured_at=None,
    )
    image_repo.save(img, raw_bytes=b"\x00\x00\x00\x00")
    image_repo.update_comment(img.id, "added later")
    assert image_repo.get(img.id).comment == "added later"


def test_update_comment_with_none_removes_sidecar(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path)
    vehicle_repo = FilesystemVehicleRepository(backend)
    repair_repo = FilesystemRepairRepository(backend)
    image_repo = FilesystemImageRepository(backend)
    vehicle = _seed_vehicle(vehicle_repo)
    repair = _seed_repair(repair_repo, vehicle.id)

    img = Image(
        id=ULID(), repair_id=repair.id, storage_key="", thumbnail_key=None,
        filename="x.jpg", mime_type="image/jpeg", size_bytes=4,
        source=ImageSource.MANUAL, uploaded_at=datetime.now(UTC), captured_at=None,
        comment="initial",
    )
    image_repo.save(img, raw_bytes=b"\x00\x00\x00\x00")
    image_repo.update_comment(img.id, None)
    assert image_repo.get(img.id).comment is None
    sidecar_path = tmp_path / "12345" / repair_dir_name(repair.date, repair.description) / f"0001_{img.id!s}.json"
    assert not sidecar_path.exists()


def test_update_comment_unknown_image_raises(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path)
    image_repo = FilesystemImageRepository(backend)
    with pytest.raises(ImageNotFound):
        image_repo.update_comment(ULID(), "x")
```

Falls die Helfer `_seed_vehicle`/`_seed_repair` in der Datei nicht existieren, oben definieren. Beispiel-Helfer (am Anfang der Datei, vor den Tests):

```python
def _seed_vehicle(vehicle_repo: FilesystemVehicleRepository) -> Vehicle:
    vehicle = Vehicle(
        id=VehicleId("12345"), vin=None, description=None,
        created_at=datetime.now(UTC),
    )
    vehicle_repo.save(vehicle)
    return vehicle


def _seed_repair(repair_repo: FilesystemRepairRepository, vehicle_id: VehicleId) -> Repair:
    repair = Repair(
        id=ULID(), vehicle_id=vehicle_id, date=date(2026, 5, 10),
        description="brakes", created_at=datetime.now(UTC),
    )
    repair_repo.save(repair)
    return repair
```

Imports oben in der Test-Datei: `from datetime import UTC, date, datetime`, `from pathlib import Path`, `import pytest`, `from ulid import ULID`, `from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle`, `from edelrep.domain.exceptions import ImageNotFound`, `from edelrep.domain.value_objects import VehicleId`, `from edelrep.infrastructure.filesystem import FilesystemImageRepository, FilesystemRepairRepository, FilesystemVehicleRepository`, `from edelrep.infrastructure.filesystem.layout import repair_dir_name`, `from edelrep.infrastructure.storage import LocalFilesystemBackend`.

- [ ] **Step 6.2: Tests laufen — Fail erwartet**

Run: `uv run pytest tests/infrastructure/filesystem/test_image_store.py -v -k "comment or sidecar"`
Expected: alle neuen Tests scheitern (`AttributeError`, `TypeError` o.ä.).

- [ ] **Step 6.3: `FilesystemImageRepository` erweitern**

In `src/edelrep/infrastructure/filesystem/image_store.py` Komplettersatz der Datei:

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
    image_sidecar_key,
    is_image_key,
    is_repair_sidecar_key,
    thumbnail_key,
)
from edelrep.infrastructure.filesystem.sidecar import (
    read_backend_sidecar,
    write_backend_sidecar,
)

_IMAGE_FILE_RE = re.compile(r"^(\d{4})_([0-9A-HJKMNP-TV-Z]{26})\.([a-zA-Z0-9]+)$")


class FilesystemImageRepository:
    """ImageRepository implementation against any StorageBackend.

    Per-image sidecar: ``<reg>/<repair-dir>/NNNN_<ulid>.json`` carries
    optional fields like ``comment``. Absence = no comment.
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
                repair_id = self._repair_id_for_image_key(key)
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
        prefix = f"{reg_no}/{dir_name}/"
        existing = sum(1 for k in self._backend.list_prefix(prefix) if is_image_key(k))
        seq = existing + 1
        parts = image.filename.rsplit(".", 1)
        extension = (parts[1] if len(parts) == 2 and parts[1] else "bin").lower()
        vehicle_id = VehicleId(reg_no)
        name = image_filename(seq=seq, image_id=image.id, extension=extension)
        self._backend.write_bytes(image_key(vehicle_id, dir_name, name), raw_bytes)
        if thumbnail_bytes is not None:
            self._backend.write_bytes(thumbnail_key(vehicle_id, dir_name, name), thumbnail_bytes)
        if image.comment is not None:
            write_backend_sidecar(
                self._backend,
                image_sidecar_key(vehicle_id, dir_name, name),
                {"comment": image.comment},
            )

    def list_for_repair(self, repair_id: ULID) -> Iterable[Image]:
        repair_path = self._find_repair_path(repair_id)
        if repair_path is None:
            return
        reg_no, dir_name = repair_path
        prefix = f"{reg_no}/{dir_name}/"
        keys = sorted(k for k in self._backend.list_prefix(prefix) if is_image_key(k))
        for key in keys:
            yield self._reconstruct(key, repair_id)

    def update_comment(self, image_id: ULID, comment: str | None) -> None:
        for key in self._backend.list_prefix(""):
            if not is_image_key(key):
                continue
            filename = key.rsplit("/", 1)[1]
            match = _IMAGE_FILE_RE.match(filename)
            if match and ULID.from_str(match.group(2)) == image_id:
                reg_no, dir_name, name = key.split("/", 2)
                vehicle_id = VehicleId(reg_no)
                sidecar = image_sidecar_key(vehicle_id, dir_name, name)
                if comment is None:
                    if self._backend.exists(sidecar):
                        self._backend.delete(sidecar)
                else:
                    write_backend_sidecar(self._backend, sidecar, {"comment": comment})
                return
        raise ImageNotFound(image_id)

    def _find_repair_path(self, repair_id: ULID) -> tuple[str, str] | None:
        for key in self._backend.list_prefix(""):
            if not is_repair_sidecar_key(key):
                continue
            data = read_backend_sidecar(self._backend, key)
            if str(data.get("id")) == str(repair_id):
                reg_no, dir_name, _ = key.split("/", 2)
                return reg_no, dir_name
        return None

    def _repair_id_for_image_key(self, key: str) -> ULID:
        reg_no, dir_name, _ = key.split("/", 2)
        sidecar = f"{reg_no}/{dir_name}/_repair.json"
        data = read_backend_sidecar(self._backend, sidecar)
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

        reg_no, dir_name, _ = key.split("/", 2)
        sidecar = image_sidecar_key(VehicleId(reg_no), dir_name, filename)
        comment: str | None = None
        if self._backend.exists(sidecar):
            data = read_backend_sidecar(self._backend, sidecar)
            raw_comment = data.get("comment")
            if isinstance(raw_comment, str):
                comment = raw_comment

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
            comment=comment,
        )
```

- [ ] **Step 6.4: `StorageBackend.delete` prüfen**

Run: `grep -n "def delete" src/edelrep/domain/ports/storage_backend.py src/edelrep/infrastructure/storage/`
Falls keine `delete`-Methode existiert, ergänzen:

In `src/edelrep/domain/ports/storage_backend.py` zur Protocol-Klasse hinzufügen:

```python
    def delete(self, key: str) -> None:
        """Delete the entry at ``key``. No-op if the entry is already absent."""
        ...
```

In `src/edelrep/infrastructure/storage/local_filesystem.py` (oder Äquivalent) Implementierung:

```python
    def delete(self, key: str) -> None:
        target = self._root / key
        try:
            target.unlink()
        except FileNotFoundError:
            return
```

Falls bereits `delete` als `remove` o.ä. existiert, statt obigem in `image_store.py` den vorhandenen Namen verwenden.

- [ ] **Step 6.5: Tests grün**

Run: `uv run pytest tests/infrastructure/filesystem/test_image_store.py -v`
Expected: alle grün.

- [ ] **Step 6.6: Committen**

```bash
git add src/edelrep/infrastructure/filesystem/image_store.py src/edelrep/domain/ports/storage_backend.py src/edelrep/infrastructure/storage/ tests/infrastructure/filesystem/test_image_store.py
git commit -m "feat(filesystem): persist optional image comments via per-image sidecar"
```

---

## Task 7: Infra — Watcher mit Image-Sidecar-Routing

**Files:**
- Modify: `src/edelrep/infrastructure/watcher/key_mapper.py`
- Modify: `src/edelrep/infrastructure/watcher/live_index.py`
- Modify: `tests/infrastructure/watcher/` (passender Test)

- [ ] **Step 7.1: Failing Test schreiben**

Im `tests/infrastructure/watcher/`-Ordner Tests prüfen mit `ls tests/infrastructure/watcher/`. Eine passende Test-Datei (z. B. `test_live_index.py`) erweitern oder `tests/infrastructure/watcher/test_image_sidecar_routing.py` anlegen:

```python
import time
from datetime import UTC, datetime
from pathlib import Path

from ulid import ULID

from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.index import SqliteIndexProjector, open_index_database
from edelrep.infrastructure.storage import LocalFilesystemBackend
from edelrep.infrastructure.watcher.key_mapper import EntityKind, classify
from edelrep.infrastructure.watcher.live_index import LiveIndex


def test_classify_image_sidecar_returns_image_sidecar() -> None:
    key = "12345/2026-05-10__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.json"
    assert classify(key) is EntityKind.IMAGE_SIDECAR


def test_live_index_re_upserts_image_on_sidecar_write(tmp_path: Path) -> None:
    storage = tmp_path / "store"
    storage.mkdir()
    backend = LocalFilesystemBackend(storage)
    vrepo = FilesystemVehicleRepository(backend)
    rrepo = FilesystemRepairRepository(backend)
    irepo = FilesystemImageRepository(backend)

    vehicle = Vehicle(id=VehicleId("12345"), vin=None, description=None, created_at=datetime.now(UTC))
    vrepo.save(vehicle)
    repair = Repair(id=ULID(), vehicle_id=vehicle.id, date=datetime.now(UTC).date(),
                    description="brakes", created_at=datetime.now(UTC))
    rrepo.save(repair)
    img = Image(id=ULID(), repair_id=repair.id, storage_key="", thumbnail_key=None,
                filename="x.jpg", mime_type="image/jpeg", size_bytes=4,
                source=ImageSource.MANUAL, uploaded_at=datetime.now(UTC),
                captured_at=None, comment=None)
    irepo.save(img, raw_bytes=b"\x00\x00\x00\x00")

    conn, lock = open_index_database(tmp_path / "index.db")
    projector = SqliteIndexProjector(conn, lock)
    live = LiveIndex(
        storage_root=storage, projector=projector,
        vehicle_repo=vrepo, repair_repo=rrepo, image_repo=irepo,
        debounce_seconds=0.05,
    )
    live.start()
    try:
        irepo.update_comment(img.id, "a comment")
        time.sleep(0.3)  # 50ms debounce + slack
        # Image is still indexed (no row deletion despite sidecar event).
        cur = conn.execute("SELECT COUNT(*) FROM images WHERE id = ?", (str(img.id),))
        assert cur.fetchone()[0] == 1
    finally:
        live.stop()
        conn.close()
```

- [ ] **Step 7.2: Tests laufen — Fail erwartet**

Run: `uv run pytest tests/infrastructure/watcher/test_image_sidecar_routing.py -v` (oder gewählte Datei)
Expected: `EntityKind.IMAGE_SIDECAR` existiert nicht.

- [ ] **Step 7.3: `EntityKind` und `classify` erweitern**

`src/edelrep/infrastructure/watcher/key_mapper.py` ersetzen durch:

```python
import re
from enum import Enum, auto
from pathlib import Path

from edelrep.infrastructure.filesystem.layout import (
    is_image_key,
    is_image_sidecar_key,
    is_repair_sidecar_key,
    is_vehicle_sidecar_key,
)

_TEMP_SUFFIX_RE = re.compile(r"\.tmp\.[0-9a-f]+$")
_THUMB_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}/\d{4}-\d{2}-\d{2}__[a-z0-9-]+/_thumbs/.+$")


class EntityKind(Enum):
    VEHICLE = auto()
    REPAIR = auto()
    IMAGE = auto()
    IMAGE_SIDECAR = auto()
    THUMBNAIL = auto()
    IGNORED = auto()


def path_to_key(path: Path, storage_root: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(storage_root.resolve())
    except ValueError:
        return None
    posix = relative.as_posix()
    return "" if posix == "." else posix


def classify(key: str) -> EntityKind:
    if _THUMB_KEY_RE.match(key):
        return EntityKind.THUMBNAIL
    if is_vehicle_sidecar_key(key):
        return EntityKind.VEHICLE
    if is_repair_sidecar_key(key):
        return EntityKind.REPAIR
    if is_image_sidecar_key(key):
        return EntityKind.IMAGE_SIDECAR
    if is_image_key(key):
        return EntityKind.IMAGE
    return EntityKind.IGNORED


def is_temp_atomic_write(path: Path) -> bool:
    return bool(_TEMP_SUFFIX_RE.search(path.name))
```

- [ ] **Step 7.4: `live_index.py` Routing erweitern**

In `src/edelrep/infrastructure/watcher/live_index.py` die Methode `_apply_batch` aktualisieren — der Block:

```python
                if kind is EntityKind.VEHICLE:
                    self._handle_vehicle(key)
                elif kind is EntityKind.REPAIR:
                    self._handle_repair(key)
                elif kind is EntityKind.IMAGE:
                    self._handle_image(key)
```

wird ersetzt durch:

```python
                if kind is EntityKind.VEHICLE:
                    self._handle_vehicle(key)
                elif kind is EntityKind.REPAIR:
                    self._handle_repair(key)
                elif kind is EntityKind.IMAGE:
                    self._handle_image(key)
                elif kind is EntityKind.IMAGE_SIDECAR:
                    self._handle_image(key)
```

(Der `_handle_image`-Pfad findet das passende Image-File anhand des Repair-Dir-Names; ULID im Sidecar-Filename ist identisch mit dem Bild, deshalb funktioniert dieselbe Routine.)

- [ ] **Step 7.5: `event_handler` filtert IMAGE_SIDECAR NICHT raus**

In `src/edelrep/infrastructure/watcher/event_handler.py` sicherstellen, dass `_IGNORED_KINDS` nur `IGNORED` und `THUMBNAIL` enthält (sollte schon der Fall sein — keine Änderung nötig, nur prüfen):

Run: `grep "_IGNORED_KINDS" src/edelrep/infrastructure/watcher/event_handler.py`
Expected: `_IGNORED_KINDS = {EntityKind.IGNORED, EntityKind.THUMBNAIL}` — unverändert.

- [ ] **Step 7.6: Tests grün**

Run: `uv run pytest tests/infrastructure/watcher/ -v`
Expected: alle Tests, alt + neu, grün.

- [ ] **Step 7.7: Committen**

```bash
git add src/edelrep/infrastructure/watcher/key_mapper.py src/edelrep/infrastructure/watcher/live_index.py tests/infrastructure/watcher/
git commit -m "feat(watcher): route image-sidecar events to image upsert (no drift)"
```

---

## Task 8: Infra — `SqliteSearchIndex.list_vehicles_by_activity`

**Files:**
- Modify: `src/edelrep/infrastructure/index/sqlite_search_index.py`
- Modify: `tests/infrastructure/index/test_sqlite_search_index.py` (oder gleichwertige Datei)

- [ ] **Step 8.1: Failing Tests schreiben**

Existierende Tests prüfen mit `ls tests/infrastructure/index/`. In passende Datei (z. B. `test_sqlite_search_index.py`) anhängen:

```python
def test_list_vehicles_by_activity_orders_by_latest_repair(tmp_path: Path) -> None:
    conn, lock = open_index_database(tmp_path / "idx.db")
    projector = SqliteIndexProjector(conn, lock)
    index = SqliteSearchIndex(conn, lock)
    try:
        old = Vehicle(id=VehicleId("AAA"), vin=None, description=None,
                      created_at=datetime(2026, 1, 1, tzinfo=UTC))
        new = Vehicle(id=VehicleId("BBB"), vin=None, description=None,
                      created_at=datetime(2026, 1, 1, tzinfo=UTC))
        projector.upsert_vehicle(old)
        projector.upsert_vehicle(new)
        # Add a repair to BBB (newer ULID → newer)
        time.sleep(0.01)
        recent_repair = Repair(
            id=ULID(), vehicle_id=new.id, date=date(2026, 5, 10),
            description="brakes", created_at=datetime.now(UTC),
        )
        projector.upsert_repair(recent_repair)

        results = list(index.list_vehicles_by_activity(limit=10))
        ids = [v.id.registration_number for v in results]
        assert ids.index("BBB") < ids.index("AAA")
    finally:
        conn.close()


def test_list_vehicles_by_activity_limit_zero_returns_empty(tmp_path: Path) -> None:
    conn, lock = open_index_database(tmp_path / "idx.db")
    index = SqliteSearchIndex(conn, lock)
    try:
        assert list(index.list_vehicles_by_activity(limit=0)) == []
    finally:
        conn.close()


def test_list_vehicles_by_activity_uses_created_at_when_no_activity(tmp_path: Path) -> None:
    conn, lock = open_index_database(tmp_path / "idx.db")
    projector = SqliteIndexProjector(conn, lock)
    index = SqliteSearchIndex(conn, lock)
    try:
        older = Vehicle(id=VehicleId("AAA"), vin=None, description=None,
                        created_at=datetime(2026, 1, 1, tzinfo=UTC))
        newer = Vehicle(id=VehicleId("BBB"), vin=None, description=None,
                        created_at=datetime(2026, 5, 1, tzinfo=UTC))
        projector.upsert_vehicle(older)
        projector.upsert_vehicle(newer)
        results = list(index.list_vehicles_by_activity(limit=10))
        ids = [v.id.registration_number for v in results]
        assert ids.index("BBB") < ids.index("AAA")
    finally:
        conn.close()
```

Imports oben prüfen / ergänzen: `import time`, `from datetime import UTC, date, datetime`, `from pathlib import Path`, `from ulid import ULID`, `from edelrep.domain.entities import Repair, Vehicle`, `from edelrep.domain.value_objects import VehicleId`, `from edelrep.infrastructure.index import SqliteIndexProjector, SqliteSearchIndex, open_index_database`.

- [ ] **Step 8.2: Tests laufen — Fail erwartet**

Run: `uv run pytest tests/infrastructure/index/test_sqlite_search_index.py -v -k "activity"`
Expected: `AttributeError: 'SqliteSearchIndex' object has no attribute 'list_vehicles_by_activity'`.

- [ ] **Step 8.3: Methode implementieren**

In `src/edelrep/infrastructure/index/sqlite_search_index.py` Imports oben ergänzen:

```python
from ulid import ULID
```

Und Methode innerhalb der Klasse hinzufügen (vor `search_vehicles` oder `upsert_vehicle`):

```python
    def list_vehicles_by_activity(self, limit: int) -> Iterable[Vehicle]:
        if limit < 1:
            return []
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT v.registration_number, v.vin, v.description, v.created_at,
                       (SELECT MAX(id) FROM repairs
                        WHERE registration_number = v.registration_number) AS last_repair_id,
                       (SELECT MAX(i.id) FROM images i
                        JOIN repairs r ON r.id = i.repair_id
                        WHERE r.registration_number = v.registration_number) AS last_image_id
                FROM vehicles v
                """
            ).fetchall()

        enriched: list[tuple[datetime, Vehicle]] = []
        for row in rows:
            vehicle = _row_to_vehicle(row)
            candidates: list[datetime] = [vehicle.created_at]
            for col in ("last_repair_id", "last_image_id"):
                ulid_str = row[col]
                if ulid_str:
                    candidates.append(ULID.from_str(ulid_str).datetime)
            enriched.append((max(candidates), vehicle))

        enriched.sort(key=lambda t: t[0], reverse=True)
        return [v for _, v in enriched[:limit]]
```

- [ ] **Step 8.4: Tests grün**

Run: `uv run pytest tests/infrastructure/index/ -v`
Expected: alle grün.

- [ ] **Step 8.5: Committen**

```bash
git add src/edelrep/infrastructure/index/sqlite_search_index.py tests/infrastructure/index/
git commit -m "feat(index): add list_vehicles_by_activity (ULID timestamps + created_at)"
```

---

## Task 9: Infra — Repair-Tiebreaker

**Files:**
- Modify: `src/edelrep/infrastructure/filesystem/repair_store.py`
- Modify: `tests/infrastructure/filesystem/test_repair_store.py` (oder gleichwertig)

- [ ] **Step 9.1: Failing Test schreiben**

Existierenden Test prüfen mit `grep -rn "list_for_vehicle" tests/infrastructure/filesystem/`. In passender Datei (z. B. `test_repair_store.py`) anhängen:

```python
def test_list_for_vehicle_same_date_orders_by_created_at_desc(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path)
    vehicle_repo = FilesystemVehicleRepository(backend)
    repair_repo = FilesystemRepairRepository(backend)
    vehicle = Vehicle(id=VehicleId("12345"), vin=None, description=None,
                      created_at=datetime.now(UTC))
    vehicle_repo.save(vehicle)

    earlier = Repair(
        id=ULID(), vehicle_id=vehicle.id, date=date(2026, 5, 10),
        description="brakes", created_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
    )
    later = Repair(
        id=ULID(), vehicle_id=vehicle.id, date=date(2026, 5, 10),
        description="oil change", created_at=datetime(2026, 5, 10, 15, 0, tzinfo=UTC),
    )
    repair_repo.save(earlier)
    repair_repo.save(later)

    results = list(repair_repo.list_for_vehicle(vehicle.id))
    assert results[0].description == "oil change"
    assert results[1].description == "brakes"
```

Imports oben prüfen / ergänzen.

- [ ] **Step 9.2: Test laufen — Fail erwartet**

Run: `uv run pytest tests/infrastructure/filesystem/test_repair_store.py -v -k "tiebreak or same_date"`
Expected: Test failt (Reihenfolge nicht deterministisch — könnte gelegentlich auch zufällig passen; deshalb sortier-Logik checken).

- [ ] **Step 9.3: Sortierschlüssel ändern**

In `src/edelrep/infrastructure/filesystem/repair_store.py` Z. 78 ersetzen:

Vorher:

```python
        repairs.sort(key=lambda r: r.date, reverse=True)
```

Nachher:

```python
        repairs.sort(key=lambda r: (r.date, r.created_at), reverse=True)
```

- [ ] **Step 9.4: Tests grün**

Run: `uv run pytest tests/infrastructure/filesystem/test_repair_store.py -v`
Expected: alle grün.

- [ ] **Step 9.5: Committen**

```bash
git add src/edelrep/infrastructure/filesystem/repair_store.py tests/infrastructure/filesystem/test_repair_store.py
git commit -m "fix(repair): stable tiebreaker by created_at after date DESC"
```

---

## Task 10: Application — `UploadImageUseCase` mit `comment`, neuer `UpdateImageCommentUseCase`

**Files:**
- Modify: `src/edelrep/application/upload_image.py`
- Create: `src/edelrep/application/update_image_comment.py`
- Modify: `src/edelrep/application/__init__.py`
- Modify: `tests/application/test_upload_image.py`
- Create: `tests/application/test_update_image_comment.py`

- [ ] **Step 10.1: Fakes erweitern**

In `tests/application/fakes.py` zwei Stellen anpassen:

(a) In `InMemoryImageRepo.save`, das `populated`-`Image`-Objekt um `comment=image.comment` ergänzen. Konkret die `Image(...)`-Konstruktion komplett ersetzen durch:

```python
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
            comment=image.comment,
        )
```

(b) Neue Methode `update_comment` in `InMemoryImageRepo` direkt nach `list_for_repair`:

```python
    def update_comment(self, image_id: ULID, comment: str | None) -> None:
        if image_id not in self._store:
            raise ImageNotFound(image_id)
        img, raw, thumb = self._store[image_id]
        updated = Image(
            id=img.id, repair_id=img.repair_id, storage_key=img.storage_key,
            thumbnail_key=img.thumbnail_key, filename=img.filename,
            mime_type=img.mime_type, size_bytes=img.size_bytes,
            source=img.source, uploaded_at=img.uploaded_at,
            captured_at=img.captured_at, comment=comment,
        )
        self._store[image_id] = (updated, raw, thumb)
```

- [ ] **Step 10.2: Failing Test in `test_upload_image.py` schreiben**

Am Ende der Datei `tests/application/test_upload_image.py` anhängen:

```python
def test_upload_image_with_comment_persists_comment(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_repair: Repair,
) -> None:
    repair_repo.save(sample_repair)
    use_case = _make_use_case(repair_repo, image_repo)
    image = use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"raw",
        filename="foo.jpg",
        comment="brakes left front",
    )
    assert image.comment == "brakes left front"
    assert image_repo.get(image.id).comment == "brakes left front"


def test_upload_image_normalises_whitespace_only_comment_to_none(
    repair_repo: InMemoryRepairRepo,
    image_repo: InMemoryImageRepo,
    sample_repair: Repair,
) -> None:
    repair_repo.save(sample_repair)
    use_case = _make_use_case(repair_repo, image_repo)
    image = use_case.execute(
        repair_id=sample_repair.id,
        raw_bytes=b"raw",
        filename="foo.jpg",
        comment="   ",
    )
    assert image.comment is None
```

- [ ] **Step 10.3: Tests laufen — Fail erwartet**

Run: `uv run pytest tests/application/test_upload_image.py -v -k "comment"`
Expected: `TypeError: execute() got an unexpected keyword argument 'comment'`.

- [ ] **Step 10.4: `UploadImageUseCase.execute` erweitern**

In `src/edelrep/application/upload_image.py` die `execute`-Signatur und den `Image`-Aufruf ergänzen:

```python
    def execute(
        self,
        *,
        repair_id: ULID,
        raw_bytes: bytes,
        filename: str,
        source: ImageSource = ImageSource.MANUAL,
        comment: str | None = None,
    ) -> Image:
        # Raises RepairNotFound if the repair doesn't exist.
        self._repair_repo.get(repair_id)

        processed = self._processor.process(raw_bytes)

        # Duplicate-check on processed bytes (what would be stored on disk).
        incoming_size = len(processed.rotated_bytes)
        incoming_hash = hashlib.sha256(processed.rotated_bytes).digest()
        for existing in self._image_repo.list_for_repair(repair_id):
            if existing.size_bytes != incoming_size:
                continue
            existing_raw = self._backend.read_bytes(existing.storage_key)
            if hashlib.sha256(existing_raw).digest() == incoming_hash:
                raise DuplicateImage(repair_id=repair_id, existing_filename=existing.filename)

        normalised_comment = (comment.strip() if comment else None) or None

        image = Image(
            id=ULID(),
            repair_id=repair_id,
            storage_key="",
            thumbnail_key=None,
            filename=filename,
            mime_type=processed.mime_type,
            size_bytes=len(processed.rotated_bytes),
            source=source,
            uploaded_at=datetime.now(UTC),
            captured_at=processed.captured_at,
            comment=normalised_comment,
        )

        self._image_repo.save(
            image,
            raw_bytes=processed.rotated_bytes,
            thumbnail_bytes=processed.thumbnail_bytes,
        )
        return self._image_repo.get(image.id)
```

- [ ] **Step 10.5: Tests grün**

Run: `uv run pytest tests/application/test_upload_image.py -v`
Expected: alle grün.

- [ ] **Step 10.6: `UpdateImageCommentUseCase` als TDD-Schritt**

`tests/application/test_update_image_comment.py` anlegen:

```python
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ulid import ULID

from edelrep.application.update_image_comment import UpdateImageCommentUseCase
from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
from edelrep.domain.exceptions import ImageNotFound
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.storage import LocalFilesystemBackend


def _bootstrap(tmp_path: Path):
    backend = LocalFilesystemBackend(tmp_path)
    vrepo = FilesystemVehicleRepository(backend)
    rrepo = FilesystemRepairRepository(backend)
    irepo = FilesystemImageRepository(backend)
    vehicle = Vehicle(id=VehicleId("12345"), vin=None, description=None, created_at=datetime.now(UTC))
    vrepo.save(vehicle)
    repair = Repair(id=ULID(), vehicle_id=vehicle.id, date=datetime.now(UTC).date(),
                    description="brakes", created_at=datetime.now(UTC))
    rrepo.save(repair)
    img = Image(id=ULID(), repair_id=repair.id, storage_key="", thumbnail_key=None,
                filename="x.jpg", mime_type="image/jpeg", size_bytes=4,
                source=ImageSource.MANUAL, uploaded_at=datetime.now(UTC),
                captured_at=None)
    irepo.save(img, raw_bytes=b"\x00\x00\x00\x00")
    return irepo, img


def test_update_image_comment_sets_comment(tmp_path: Path) -> None:
    irepo, img = _bootstrap(tmp_path)
    use_case = UpdateImageCommentUseCase(irepo)
    use_case.execute(img.id, "added later")
    assert irepo.get(img.id).comment == "added later"


def test_update_image_comment_normalises_whitespace_to_none(tmp_path: Path) -> None:
    irepo, img = _bootstrap(tmp_path)
    use_case = UpdateImageCommentUseCase(irepo)
    use_case.execute(img.id, "   ")
    assert irepo.get(img.id).comment is None


def test_update_image_comment_rejects_too_long(tmp_path: Path) -> None:
    irepo, img = _bootstrap(tmp_path)
    use_case = UpdateImageCommentUseCase(irepo)
    with pytest.raises(ValueError, match="too long"):
        use_case.execute(img.id, "x" * 1001)


def test_update_image_comment_unknown_image_raises(tmp_path: Path) -> None:
    irepo, _ = _bootstrap(tmp_path)
    use_case = UpdateImageCommentUseCase(irepo)
    with pytest.raises(ImageNotFound):
        use_case.execute(ULID(), "x")
```

- [ ] **Step 10.7: Tests laufen — Fail erwartet**

Run: `uv run pytest tests/application/test_update_image_comment.py -v`
Expected: `ModuleNotFoundError: edelrep.application.update_image_comment`.

- [ ] **Step 10.8: Use-Case implementieren**

`src/edelrep/application/update_image_comment.py` anlegen:

```python
from ulid import ULID

from edelrep.domain.entities import Image
from edelrep.domain.ports import ImageRepository


class UpdateImageCommentUseCase:
    """Set or clear the comment on an existing image."""

    def __init__(self, image_repo: ImageRepository) -> None:
        self._image_repo = image_repo

    def execute(self, image_id: ULID, comment: str | None) -> Image:
        normalised = (comment.strip() if comment else None) or None
        if normalised is not None and len(normalised) > 1000:
            raise ValueError("comment too long (max 1000 chars)")
        self._image_repo.update_comment(image_id, normalised)
        return self._image_repo.get(image_id)
```

- [ ] **Step 10.9: Re-Export im Application-`__init__.py`**

`src/edelrep/application/__init__.py` ergänzen:

```python
from edelrep.application.update_image_comment import UpdateImageCommentUseCase
```

und in der `__all__`-Liste `"UpdateImageCommentUseCase"` einfügen (alphabetisch passend).

- [ ] **Step 10.10: Tests grün**

Run: `uv run pytest tests/application/ -v`
Expected: alle grün.

- [ ] **Step 10.11: Committen**

```bash
git add src/edelrep/application/upload_image.py src/edelrep/application/update_image_comment.py src/edelrep/application/__init__.py tests/application/test_upload_image.py tests/application/test_update_image_comment.py
git commit -m "feat(application): UploadImageUseCase accepts comment; add UpdateImageCommentUseCase"
```

---

## Task 11: Application — `SearchVehicleUseCase` mit Fuzzy + Activity

**Files:**
- Modify: `src/edelrep/application/search_vehicle.py`
- Modify: `tests/application/test_search_vehicle.py`

- [ ] **Step 11.1: Failing Tests schreiben**

Bestehende Tests prüfen mit `cat tests/application/test_search_vehicle.py`. Datei komplett ersetzen oder erweitern:

```python
from edelrep.application.search_vehicle import SearchVehicleUseCase
from edelrep.domain.entities import Vehicle
from edelrep.domain.value_objects import VehicleId
from datetime import UTC, datetime


class _FakeIndex:
    def __init__(self, vehicles: list[Vehicle]) -> None:
        self._vehicles = vehicles

    def search_vehicles(self, query: str, limit: int = 20):  # pragma: no cover - not used
        return []

    def list_vehicles_by_activity(self, limit: int):
        return self._vehicles[:limit]

    def upsert_vehicle(self, vehicle): ...
    def remove_vehicle(self, vehicle_id): ...
    def clear(self): ...


class _AlwaysMaxMatcher:
    def score(self, query: str, candidate: str) -> float:
        return 100.0 if candidate else 0.0


class _NeverMatcher:
    def score(self, query: str, candidate: str) -> float:
        return 0.0


def _vehicle(reg: str, vin: str | None = None, desc: str | None = None) -> Vehicle:
    return Vehicle(id=VehicleId(reg), vin=vin, description=desc, created_at=datetime.now(UTC))


def test_empty_query_returns_activity_list() -> None:
    vs = [_vehicle("AAA"), _vehicle("BBB")]
    uc = SearchVehicleUseCase(_FakeIndex(vs), _NeverMatcher())
    assert uc.execute("") == vs


def test_query_with_high_score_returns_results() -> None:
    vs = [_vehicle("AAA"), _vehicle("BBB")]
    uc = SearchVehicleUseCase(_FakeIndex(vs), _AlwaysMaxMatcher())
    assert set(v.id.registration_number for v in uc.execute("ZZZ")) == {"AAA", "BBB"}


def test_query_below_threshold_returns_empty() -> None:
    vs = [_vehicle("AAA")]
    uc = SearchVehicleUseCase(_FakeIndex(vs), _NeverMatcher())
    assert uc.execute("anything") == []


def test_limit_zero_raises() -> None:
    uc = SearchVehicleUseCase(_FakeIndex([]), _NeverMatcher())
    with pytest.raises(ValueError):
        uc.execute("", limit=0)
```

Imports oben anpassen: `import pytest`.

- [ ] **Step 11.2: Tests laufen — Fail erwartet**

Run: `uv run pytest tests/application/test_search_vehicle.py -v`
Expected: `TypeError` (Konstruktor erwartet keinen `fuzzy`-Parameter) und `AttributeError` (`list_vehicles_by_activity` fehlt am Konstruktor-Empfänger).

- [ ] **Step 11.3: Use-Case erweitern**

`src/edelrep/application/search_vehicle.py` ersetzen durch:

```python
from edelrep.domain.entities import Vehicle
from edelrep.domain.ports import FuzzyMatcher, SearchIndex


class SearchVehicleUseCase:
    """Search vehicles. Empty query returns the most-recently-active vehicles."""

    SCORE_THRESHOLD = 60.0
    CANDIDATE_POOL = 1000

    def __init__(self, search_index: SearchIndex, fuzzy: FuzzyMatcher) -> None:
        self._search_index = search_index
        self._fuzzy = fuzzy

    def execute(self, query: str, limit: int = 50) -> list[Vehicle]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        q = query.strip()
        if not q:
            return list(self._search_index.list_vehicles_by_activity(limit))

        candidates = list(self._search_index.list_vehicles_by_activity(self.CANDIDATE_POOL))
        scored: list[tuple[float, int, Vehicle]] = []
        for idx, v in enumerate(candidates):
            best = max(
                self._fuzzy.score(q, v.id.registration_number),
                self._fuzzy.score(q, v.vin or ""),
                self._fuzzy.score(q, v.description or ""),
            )
            if best >= self.SCORE_THRESHOLD:
                scored.append((best, -idx, v))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return [v for _, _, v in scored[:limit]]
```

- [ ] **Step 11.4: Tests grün**

Run: `uv run pytest tests/application/test_search_vehicle.py -v`
Expected: alle 4 Tests grün.

- [ ] **Step 11.5: Committen**

```bash
git add src/edelrep/application/search_vehicle.py tests/application/test_search_vehicle.py
git commit -m "feat(search): SearchVehicleUseCase uses FuzzyMatcher; empty query returns activity list"
```

---

## Task 12: Presentation — Container-Verdrahtung

**Files:**
- Modify: `src/edelrep/presentation/container.py`

- [ ] **Step 12.1: Container ergänzen**

In `src/edelrep/presentation/container.py`:

Oben Imports ergänzen:

```python
from edelrep.application.update_image_comment import UpdateImageCommentUseCase
from edelrep.infrastructure.search.rapidfuzz_matcher import RapidFuzzMatcher
```

Im `Container`-Dataclass eine Zeile ergänzen (vor `inbox_reader`):

```python
    update_image_comment: UpdateImageCommentUseCase
```

In `build_container(...)` nach `processor = PillowImageProcessor()` und vor dem `Container(...)`-Aufruf ergänzen:

```python
    fuzzy = RapidFuzzMatcher()
```

`SearchVehicleUseCase`-Konstruktor-Aufruf ändern auf `SearchVehicleUseCase(search_index, fuzzy=fuzzy)`.

Den `Container(...)`-Aufruf erweitern um `update_image_comment=UpdateImageCommentUseCase(image_repo),`.

- [ ] **Step 12.2: Test der Container-Verdrahtung**

Run: `uv run pytest tests/presentation/ -v`
Expected: bestehende Tests grün; falls ein `test_container_email.py` oder ähnliches die Container-Felder durchgeht, muss es auch grün bleiben.

- [ ] **Step 12.3: Pyright-Check**

Run: `uv run pyright`
Expected: 0 Errors.

- [ ] **Step 12.4: Committen**

```bash
git add src/edelrep/presentation/container.py
git commit -m "feat(container): wire RapidFuzzMatcher and UpdateImageCommentUseCase"
```

---

## Task 13: Presentation — Image-Routen (`comment` Form-Field + PATCH)

**Files:**
- Modify: `src/edelrep/presentation/routes/images.py`
- Modify: `tests/presentation/test_images.py`

- [ ] **Step 13.1: Failing Tests schreiben**

In `tests/presentation/test_images.py` anhängen (Imports und Helfer wie in der Datei üblich nutzen — Stichprobe mit `head -50 tests/presentation/test_images.py`):

```python
def test_upload_image_with_comment_form_field(client: TestClient, container: Container) -> None:
    _seed_vehicle_and_repair(container, "12345")
    repair_id = _first_repair_id(container, "12345")
    file_bytes = _jpeg_bytes()
    r = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("x.jpg", file_bytes, "image/jpeg")},
        data={"comment": "brakes left"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 201
    image_id = r.json()["image_id"]
    img = container.image_repo.get(ULID.from_str(image_id))
    assert img.comment == "brakes left"


def test_patch_image_comment_sets_and_returns_value(client: TestClient, container: Container) -> None:
    _seed_vehicle_and_repair(container, "12345")
    repair_id = _first_repair_id(container, "12345")
    upload = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("x.jpg", _jpeg_bytes(), "image/jpeg")},
        headers={"Accept": "application/json"},
    )
    image_id = upload.json()["image_id"]

    r = client.patch(f"/images/{image_id}/comment", json={"comment": "updated"})
    assert r.status_code == 200
    body = r.json()
    assert body["comment"] == "updated"
    assert container.image_repo.get(ULID.from_str(image_id)).comment == "updated"


def test_patch_image_comment_null_clears(client: TestClient, container: Container) -> None:
    _seed_vehicle_and_repair(container, "12345")
    repair_id = _first_repair_id(container, "12345")
    upload = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("x.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"comment": "initial"},
        headers={"Accept": "application/json"},
    )
    image_id = upload.json()["image_id"]
    r = client.patch(f"/images/{image_id}/comment", json={"comment": None})
    assert r.status_code == 200
    assert r.json()["comment"] is None
    assert container.image_repo.get(ULID.from_str(image_id)).comment is None


def test_patch_image_comment_too_long_returns_422(client: TestClient, container: Container) -> None:
    _seed_vehicle_and_repair(container, "12345")
    repair_id = _first_repair_id(container, "12345")
    upload = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("x.jpg", _jpeg_bytes(), "image/jpeg")},
        headers={"Accept": "application/json"},
    )
    image_id = upload.json()["image_id"]
    r = client.patch(f"/images/{image_id}/comment", json={"comment": "x" * 1001})
    assert r.status_code == 422


def test_patch_unknown_image_comment_returns_404(client: TestClient) -> None:
    r = client.patch(f"/images/{ULID()!s}/comment", json={"comment": "x"})
    assert r.status_code == 404
```

Helper `_seed_vehicle_and_repair`, `_first_repair_id`, `_jpeg_bytes` aus bestehender Datei wiederverwenden, falls vorhanden. Sonst gleichwertige aus `tests/presentation/test_repairs.py` o.ä. übernehmen.

- [ ] **Step 13.2: Tests laufen — Fail erwartet**

Run: `uv run pytest tests/presentation/test_images.py -v -k "comment"`
Expected: alle 5 Tests fehlerhaft.

- [ ] **Step 13.3: Route erweitern**

In `src/edelrep/presentation/routes/images.py` erweitern: an `from fastapi import` `Form` und an FastAPI-Klassen ergänzen falls fehlt. Vollständiger Ersatz:

```python
from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from ulid import ULID

from edelrep.domain.exceptions import (
    DuplicateImage,
    ImageNotFound,
    InvalidVehicleId,
    RepairNotFound,
    VehicleNotFound,
)
from edelrep.domain.value_objects import VehicleId
from edelrep.presentation.dependencies import ContainerDep

router = APIRouter()


class CommentPayload(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)


@router.get(
    "/vehicles/{registration_number}/repairs/{repair_id}/upload",
    response_class=HTMLResponse,
)
def upload_form(
    request: Request,
    container: ContainerDep,
    registration_number: str,
    repair_id: str,
) -> HTMLResponse:
    try:
        vehicle_id = VehicleId(registration_number)
        if not container.vehicle_repo.exists(vehicle_id):
            raise VehicleNotFound(registration_number)
    except (VehicleNotFound, InvalidVehicleId) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "upload_image.html",
        {"registration_number": registration_number, "repair_id": repair_id},
    )


@router.post(
    "/vehicles/{registration_number}/repairs/{repair_id}/images",
    response_model=None,
)
def upload_image(
    request: Request,
    container: ContainerDep,
    registration_number: str,
    repair_id: str,
    image: UploadFile,
    comment: str = Form(""),
) -> RedirectResponse | JSONResponse:
    wants_json = "application/json" in request.headers.get("accept", "")
    try:
        rid = ULID.from_str(repair_id)
    except ValueError as exc:
        if wants_json:
            return JSONResponse({"error": str(exc)}, status_code=404)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raw = image.file.read()
    try:
        saved = container.upload_image.execute(
            repair_id=rid,
            raw_bytes=raw,
            filename=image.filename or "upload.jpg",
            comment=comment or None,
        )
    except RepairNotFound as exc:
        if wants_json:
            return JSONResponse({"error": str(exc)}, status_code=404)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DuplicateImage as exc:
        if wants_json:
            return JSONResponse({"error": str(exc)}, status_code=422)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        if wants_json:
            return JSONResponse({"error": str(exc)}, status_code=422)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if wants_json:
        return JSONResponse({"image_id": str(saved.id)}, status_code=201)
    return RedirectResponse(
        url=f"/vehicles/{registration_number}",
        status_code=303,
    )


@router.patch("/images/{image_id}/comment")
def patch_image_comment(
    container: ContainerDep,
    image_id: str,
    payload: CommentPayload,
) -> JSONResponse:
    try:
        iid = ULID.from_str(image_id)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    try:
        updated = container.update_image_comment.execute(iid, payload.comment)
    except ImageNotFound as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse({"image_id": str(updated.id), "comment": updated.comment})


@router.get("/images/{image_id}/raw")
def get_raw_image(
    container: ContainerDep,
    image_id: str,
) -> Response:
    try:
        iid = ULID.from_str(image_id)
        img, raw = container.get_image.execute(iid)
    except (ValueError, ImageNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=raw, media_type=img.mime_type)


@router.get("/images/{image_id}/thumbnail")
def get_thumbnail(
    container: ContainerDep,
    image_id: str,
) -> Response:
    try:
        iid = ULID.from_str(image_id)
        img = container.image_repo.get(iid)
    except (ValueError, ImageNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if img.thumbnail_key is None:
        raise HTTPException(status_code=404, detail="No thumbnail")
    raw = container.backend.read_bytes(img.thumbnail_key)
    return Response(content=raw, media_type=img.mime_type)
```

- [ ] **Step 13.4: Tests grün**

Run: `uv run pytest tests/presentation/test_images.py -v`
Expected: alle grün.

- [ ] **Step 13.5: Committen**

```bash
git add src/edelrep/presentation/routes/images.py tests/presentation/test_images.py
git commit -m "feat(routes): accept comment on upload + PATCH /images/{id}/comment"
```

---

## Task 14: Presentation — Image-Picker mit Kommentar-Textarea

**Files:**
- Modify: `src/edelrep/presentation/templates/_image_picker.html`

- [ ] **Step 14.1: Template-Eintrag erweitern**

In `_image_picker.html` im `<template data-picker-entry-template>`-Block den `<li>`-Inhalt erweitern. Suche im File nach:

```html
        <p data-entry-status class="mt-1.5"></p>
      </div>
```

Diese Zeilen ersetzen durch:

```html
        <p data-entry-status class="mt-1.5"></p>
        <textarea data-entry-comment maxlength="1000" rows="1"
                  placeholder="Kommentar (optional)"
                  class="mt-2 w-full text-sm border border-slate-200 rounded-md px-2 py-1 resize-y"></textarea>
      </div>
```

- [ ] **Step 14.2: `pickerApi.getEntries()` liefert Kommentar**

Im IIFE-Skript, in der `initPicker(root)`-Funktion, in der `addFile`-Routine das Speichern eines Entry-Records anpassen — direkt nach `const entry = { id, file, status: 'pending', el, thumbUrl, ... };` zusätzlich:

```javascript
      entry.commentEl = el.querySelector('[data-entry-comment]');
```

Und in der zurückgegebenen `root.pickerApi`:

```javascript
    root.pickerApi = {
      getEntries: () => entries.map(e => ({
        id: e.id,
        file: e.file,
        status: e.status,
        commentEl: e.commentEl,
        comment: e.commentEl ? e.commentEl.value : '',
      })),
      setStatus(id, status, message) {
        const e = entries.find(x => x.id === id);
        if (!e) return;
        e.status = status;
        setStatusBadge(e.statusEl, status, message);
        e.retryBtn.hidden = (status !== 'error');
      },
      onRetry(id, handler) {
        const e = entries.find(x => x.id === id);
        if (!e) return;
        e.retryBtn.onclick = () => handler(e);
      },
    };
```

(Bei diesem Ersatz wird `.commentEl` bewusst mit-exportiert, damit die Aufrufer in `new_repair.html`/`upload_image.html` den aktuellen Wert beim Submit auslesen können — siehe Task 15.)

- [ ] **Step 14.3: Smoke-Test**

Run: `uv run pytest tests/presentation/test_e2e_click_path.py -v` (falls Path nicht existiert, übersprungen). Mindestens visuell prüfen, dass das Template noch korrekt rendert:

```bash
uv run python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('src/edelrep/presentation/templates')); env.get_template('_image_picker.html').render()"
```

Expected: kein Jinja2-Syntax-Error.

- [ ] **Step 14.4: Committen**

```bash
git add src/edelrep/presentation/templates/_image_picker.html
git commit -m "feat(ui): add per-image comment textarea to image picker"
```

---

## Task 15: Presentation — Kommentar im Upload-JS mitsenden

**Files:**
- Modify: `src/edelrep/presentation/templates/new_repair.html`
- Modify: `src/edelrep/presentation/templates/upload_image.html`

- [ ] **Step 15.1: `new_repair.html` JS anpassen**

In `new_repair.html` die `uploadOne`-Funktion suchen. Den Block:

```javascript
  async function uploadOne(entry, baseUrl) {
    const fd = new FormData();
    fd.set('image', entry.file, entry.file.name);
```

ersetzen durch:

```javascript
  async function uploadOne(entry, baseUrl) {
    const fd = new FormData();
    fd.set('image', entry.file, entry.file.name);
    if (entry.commentEl) {
      fd.set('comment', entry.commentEl.value);
    }
```

- [ ] **Step 15.2: `upload_image.html` JS anpassen**

In `upload_image.html` denselben Block analog anpassen:

```javascript
  async function uploadOne(entry) {
    const fd = new FormData();
    fd.set('image', entry.file, entry.file.name);
    if (entry.commentEl) {
      fd.set('comment', entry.commentEl.value);
    }
```

- [ ] **Step 15.3: Smoke-Test E2E**

Run: `uv run pytest tests/presentation/test_e2e_click_path.py -v`
Expected: bestehende E2E-Tests bleiben grün (Kommentar-Feld leer = wird als leerer String gesendet → Server normalisiert auf `None`).

- [ ] **Step 15.4: Committen**

```bash
git add src/edelrep/presentation/templates/new_repair.html src/edelrep/presentation/templates/upload_image.html
git commit -m "feat(ui): send per-image comment with upload payload"
```

---

## Task 16: Presentation — Detail-Seite mit Caption + Modal

**Files:**
- Modify: `src/edelrep/presentation/templates/vehicle_detail.html`

- [ ] **Step 16.1: Thumbnail-Block ersetzen**

In `vehicle_detail.html` den Block:

```jinja
    {% if repair_images %}
    <div class="mt-4 flex gap-2 overflow-x-auto pb-1">
    {% for img in repair_images %}
      <a href="/images/{{ img.id }}/raw" target="_blank" class="flex-shrink-0">
        <img src="/images/{{ img.id }}/thumbnail" alt="{{ img.filename }}"
             class="h-24 w-24 object-cover rounded-lg ring-1 ring-slate-200 hover:ring-blue-400 transition-all">
      </a>
    {% endfor %}
    </div>
    {% endif %}
```

ersetzen durch:

```jinja
    {% if repair_images %}
    <div class="mt-4 flex gap-3 overflow-x-auto pb-1">
    {% for img in repair_images %}
      <div class="flex-shrink-0 w-24">
        <button type="button"
                class="block w-24 h-24 rounded-lg overflow-hidden ring-1 ring-slate-200 hover:ring-blue-400 transition-all"
                data-image-trigger
                data-image-id="{{ img.id }}"
                data-image-filename="{{ img.filename }}"
                data-image-comment="{{ img.comment or '' }}">
          <img src="/images/{{ img.id }}/thumbnail" alt="{{ img.filename }}"
               class="w-full h-full object-cover">
        </button>
        {% if img.comment %}
        <p class="mt-1 text-xs text-slate-600 line-clamp-2 break-words"
           data-image-caption-for="{{ img.id }}">{{ img.comment }}</p>
        {% else %}
        <p class="mt-1 text-xs text-slate-400 italic" data-image-caption-for="{{ img.id }}" hidden></p>
        {% endif %}
      </div>
    {% endfor %}
    </div>
    {% endif %}
```

- [ ] **Step 16.2: Modal + JS am Seitenende einfügen**

Direkt vor dem `{% endblock %}` des `content`-Blocks einfügen:

```jinja
<div id="image-modal" class="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" hidden>
  <div class="bg-white rounded-xl max-w-3xl w-full max-h-[90vh] overflow-auto p-4 space-y-3">
    <div class="flex justify-between items-center gap-3">
      <span data-modal-filename class="font-medium text-sm truncate"></span>
      <button type="button" data-modal-close aria-label="Schliessen"
              class="text-slate-400 hover:text-slate-900 text-2xl leading-none">×</button>
    </div>
    <img data-modal-image alt="" class="w-full h-auto rounded-lg max-h-[60vh] object-contain bg-slate-50">
    <a data-modal-raw target="_blank" class="text-sm text-blue-600 hover:underline">In neuem Tab öffnen</a>
    <form data-modal-form class="space-y-2">
      <label class="block text-sm font-medium" for="image-modal-comment">Kommentar</label>
      <textarea id="image-modal-comment" data-modal-comment maxlength="1000" rows="3"
                class="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"></textarea>
      <div class="flex justify-end items-center gap-3">
        <span data-modal-status class="text-xs text-slate-500"></span>
        <button type="submit"
                class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium">
          Speichern
        </button>
      </div>
    </form>
  </div>
</div>

<script>
(function () {
  const modal = document.getElementById('image-modal');
  if (!modal) return;
  const filenameEl = modal.querySelector('[data-modal-filename]');
  const imageEl = modal.querySelector('[data-modal-image]');
  const rawLink = modal.querySelector('[data-modal-raw]');
  const commentEl = modal.querySelector('[data-modal-comment]');
  const statusEl = modal.querySelector('[data-modal-status]');
  const form = modal.querySelector('[data-modal-form]');
  const closeBtn = modal.querySelector('[data-modal-close]');
  let activeImageId = null;

  document.querySelectorAll('[data-image-trigger]').forEach(btn => {
    btn.addEventListener('click', () => {
      activeImageId = btn.dataset.imageId;
      filenameEl.textContent = btn.dataset.imageFilename;
      imageEl.src = `/images/${activeImageId}/raw`;
      rawLink.href = `/images/${activeImageId}/raw`;
      commentEl.value = btn.dataset.imageComment || '';
      statusEl.textContent = '';
      modal.hidden = false;
    });
  });

  closeBtn.addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.hidden = true;
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!activeImageId) return;
    statusEl.textContent = 'Speichere …';
    const raw = commentEl.value.trim();
    try {
      const resp = await fetch(`/images/${activeImageId}/comment`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ comment: raw === '' ? null : raw }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        statusEl.textContent = body.error || `Fehler ${resp.status}`;
        return;
      }
      const data = await resp.json();
      // Caption auf der Liste aktualisieren
      const caption = document.querySelector(`[data-image-caption-for="${activeImageId}"]`);
      const trigger = document.querySelector(`[data-image-trigger][data-image-id="${activeImageId}"]`);
      if (caption) {
        if (data.comment) {
          caption.textContent = data.comment;
          caption.hidden = false;
          caption.classList.remove('text-slate-400', 'italic');
          caption.classList.add('text-slate-600', 'line-clamp-2', 'break-words');
        } else {
          caption.textContent = '';
          caption.hidden = true;
        }
      }
      if (trigger) trigger.dataset.imageComment = data.comment || '';
      statusEl.textContent = 'Gespeichert.';
      setTimeout(() => { modal.hidden = true; }, 600);
    } catch (err) {
      statusEl.textContent = 'Netzwerkfehler.';
    }
  });
})();
</script>
```

- [ ] **Step 16.3: Detail-Route schickt `image.comment` mit**

Sicherstellen, dass `vehicle_detail` in `routes/vehicles.py` `images_by_repair` mit den vollständigen `Image`-Objekten (inklusive `comment`) übergibt — das ist bereits der Fall, da `container.image_repo.list_for_repair(...)` jetzt `comment` mitliefert. Kein Code-Change nötig.

- [ ] **Step 16.4: Tests laufen**

Run: `uv run pytest tests/presentation/ -v`
Expected: bestehende Tests grün; Caption ist optional, alte Tests sehen nur das Detail-Markup.

Falls die bestehenden E2E-Tests (`test_e2e_click_path.py`) auf `<a href="/images/.../raw" target="_blank">` als Marker prüfen, müssen sie auf den neuen Trigger-Selektor umgestellt werden. Konkret:

Run: `grep -n "/images/.*raw" tests/presentation/test_e2e_click_path.py`
Falls Match: dort den Selektor anpassen auf `data-image-trigger` oder auf den weiterhin vorhandenen `<a data-modal-raw>` im offenen Modal.

- [ ] **Step 16.5: Committen**

```bash
git add src/edelrep/presentation/templates/vehicle_detail.html tests/presentation/
git commit -m "feat(ui): image modal with editable comment + caption preview on detail page"
```

---

## Task 17: Presentation — Suchseite mit Initial-Vollliste

**Files:**
- Modify: `src/edelrep/presentation/routes/search.py`
- Modify: `src/edelrep/presentation/templates/search.html`
- Modify: `src/edelrep/presentation/templates/_vehicle_search_results.html`
- Modify: `tests/presentation/test_search.py`

- [ ] **Step 17.1: Failing Tests schreiben**

In `tests/presentation/test_search.py` (oder anlegen):

```python
def test_search_page_initial_renders_all_vehicles(client: TestClient, container: Container) -> None:
    # Drei Fahrzeuge, eines mit jüngerer Reparatur
    from datetime import UTC, date, datetime
    from ulid import ULID
    from edelrep.domain.entities import Repair, Vehicle
    from edelrep.domain.value_objects import VehicleId
    container.vehicle_repo.save(Vehicle(
        id=VehicleId("AAA"), vin=None, description=None, created_at=datetime(2026, 1, 1, tzinfo=UTC),
    ))
    container.vehicle_repo.save(Vehicle(
        id=VehicleId("BBB"), vin=None, description=None, created_at=datetime(2026, 1, 1, tzinfo=UTC),
    ))
    container.projector.full_rebuild(container.vehicle_repo, container.repair_repo, container.image_repo)
    r = client.get("/search")
    assert r.status_code == 200
    body = r.text
    assert "AAA" in body
    assert "BBB" in body


def test_search_suggestions_empty_query_returns_all(client: TestClient, container: Container) -> None:
    from datetime import UTC, datetime
    from edelrep.domain.entities import Vehicle
    from edelrep.domain.value_objects import VehicleId
    container.vehicle_repo.save(Vehicle(
        id=VehicleId("XYZ"), vin=None, description=None, created_at=datetime.now(UTC),
    ))
    container.projector.full_rebuild(container.vehicle_repo, container.repair_repo, container.image_repo)
    r = client.get("/search/suggestions?q=")
    assert r.status_code == 200
    assert "XYZ" in r.text


def test_search_suggestions_fuzzy_typo_finds_vehicle(client: TestClient, container: Container) -> None:
    from datetime import UTC, datetime
    from edelrep.domain.entities import Vehicle
    from edelrep.domain.value_objects import VehicleId
    container.vehicle_repo.save(Vehicle(
        id=VehicleId("12345"), vin=None, description=None, created_at=datetime.now(UTC),
    ))
    container.projector.full_rebuild(container.vehicle_repo, container.repair_repo, container.image_repo)
    r = client.get("/search/suggestions?q=12354")  # typo
    assert r.status_code == 200
    assert "12345" in r.text


def test_search_suggestions_no_matches_message(client: TestClient) -> None:
    r = client.get("/search/suggestions?q=Z9Z9Z9")
    assert r.status_code == 200
    assert "Keine Treffer" in r.text or "Keine Fahrzeuge" in r.text
```

- [ ] **Step 17.2: Tests laufen — Fail erwartet**

Run: `uv run pytest tests/presentation/test_search.py -v`
Expected: mindestens `test_search_page_initial_renders_all_vehicles` failt — `/search` heute zeigt leere Liste.

- [ ] **Step 17.3: Route umbauen**

`src/edelrep/presentation/routes/search.py` ersetzen durch:

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from edelrep.presentation.dependencies import ContainerDep

router = APIRouter()


@router.get("/search", response_class=HTMLResponse)
def search_page(request: Request, container: ContainerDep) -> HTMLResponse:
    templates = request.app.state.templates
    results = container.search_vehicle.execute("", limit=200)
    return templates.TemplateResponse(
        request,
        "search.html",
        {"results": results, "is_empty_filter": False},
    )


@router.get("/search/suggestions", response_class=HTMLResponse)
def suggestions(
    request: Request,
    container: ContainerDep,
    q: str = "",
) -> HTMLResponse:
    templates = request.app.state.templates
    results = container.search_vehicle.execute(q)
    return templates.TemplateResponse(
        request,
        "_vehicle_search_results.html",
        {"results": results, "is_empty_filter": bool(q.strip())},
    )
```

- [ ] **Step 17.4: `search.html` Placeholder anpassen**

In `src/edelrep/presentation/templates/search.html` den `placeholder`-Attributwert ersetzen durch `"Stammnummer, Rahmennummer oder Beschreibung – Tippfehler erlaubt"`. Das `is_empty_filter`-Flag wird vom Render an `_vehicle_search_results.html` durchgereicht (es liegt im Kontext, weil das Include den Parent-Context erbt).

- [ ] **Step 17.5: `_vehicle_search_results.html` differenzieren**

`src/edelrep/presentation/templates/_vehicle_search_results.html` ersetzen durch:

```jinja
{% if results %}
<ul class="space-y-3">
{% for v in results %}
  <li>
    <a href="/vehicles/{{ v.id.registration_number }}"
       class="block bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:border-blue-300 transition-all">
      <div class="text-xl font-semibold tracking-tight">{{ v.id.registration_number }}</div>
      {% if v.vin %}<div class="text-sm text-slate-600 mt-1">Rahmennummer: <span class="font-mono">{{ v.vin }}</span></div>{% endif %}
      {% if v.description %}<div class="text-sm text-slate-700 mt-1">{{ v.description }}</div>{% endif %}
    </a>
  </li>
{% endfor %}
</ul>
{% elif is_empty_filter %}
<p class="text-slate-500 text-center py-8">Keine Treffer.</p>
{% else %}
<p class="text-slate-500 text-center py-8">Noch keine Fahrzeuge angelegt.</p>
{% endif %}
```

- [ ] **Step 17.6: Tests grün**

Run: `uv run pytest tests/presentation/test_search.py -v`
Expected: alle 4 Tests grün. Bestehende Suggestions-Tests bleiben grün (Fuzzy-Threshold 60 lässt exakte Treffer durch).

- [ ] **Step 17.7: Committen**

```bash
git add src/edelrep/presentation/routes/search.py src/edelrep/presentation/templates/search.html src/edelrep/presentation/templates/_vehicle_search_results.html tests/presentation/test_search.py
git commit -m "feat(ui): /search shows all vehicles by last activity, fuzzy filtering"
```

---

## Task 18: Doku — Architektur-Doku-Update

**Files:**
- Modify: `docs/architecture.md`

- [ ] **Step 18.1: Sidecar-Sektion anpassen**

In `docs/architecture.md` den Abschnitt suchen, der mit "Pro Bild gibt es **keine** Sidecar-Datei in V1" anfängt. Diesen Satz (und die ihn umgebende Aussage über `MANUAL`/`captured_at`) ersetzen durch:

```markdown
Pro Bild gibt es einen **optionalen** Sidecar `NNNN_<ulid>.json` (`schema_version: 1`) neben der Bilddatei. Aktuell enthält er nur das Feld `comment` (max 1000 Zeichen). Die Quelle (`manual` vs. `email`) und die EXIF-Capture-Time werden weiterhin nicht persistiert — beim Lesen sind die Defaults `manual` / `None`. Image-Sidecars werden vom Watcher als Image-Events behandelt (sie triggern keinen Drift).
```

Falls weitere Stellen in der Doku Image-Sidecars erwähnen, dort ebenfalls aktualisieren (`grep -n "keine.*Sidecar" docs/architecture.md`).

- [ ] **Step 18.2: Committen**

```bash
git add docs/architecture.md
git commit -m "docs: document optional per-image sidecar"
```

---

## Task 19: Abschluss — Volltest und Quality Gates

**Files:** keine Änderungen

- [ ] **Step 19.1: Volle Test-Suite**

Run: `uv run pytest --cov=edelrep`
Expected: alle Tests grün, Coverage ≥ 95% gesamt; neue Dateien ≥ 90%.

- [ ] **Step 19.2: Pyright**

Run: `uv run pyright`
Expected: 0 Errors.

- [ ] **Step 19.3: Ruff**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean. Falls Format-Fehler: `uv run ruff format .` und commit.

- [ ] **Step 19.4: Domain-Import-Guard**

Run: `! grep -REn "fastapi|sqlalchemy|fsspec|jinja2|uvicorn|httpx|pillow|watchdog|apscheduler|imap_tools|rapidfuzz" src/edelrep/domain/`
Expected: exit-code 0 (kein Match) — `rapidfuzz` darf NICHT in Domain auftauchen.

- [ ] **Step 19.5: Application-Import-Guard**

Run: `! grep -REn "fastapi|jinja2|uvicorn|httpx|pillow|watchdog|imap_tools|apscheduler" src/edelrep/application/`
Expected: exit-code 0. (`rapidfuzz` darf nicht direkt in `application/` referenziert sein — das passiert nur via Port `FuzzyMatcher`. Wenn `grep -REn "rapidfuzz" src/edelrep/application/` einen Treffer zeigt, refactoren.)

- [ ] **Step 19.6: Manuelles Smoke-Testing**

Run:
```bash
rm -f index.db index.db-shm index.db-wal
uv run edelrep serve --storage-root ./storage --index-path ./index.db &
SERVER_PID=$!
sleep 2
curl -fsS http://127.0.0.1:8080/search > /dev/null && echo "search OK"
kill $SERVER_PID
```
Expected: "search OK". Server-Aufruf wirft keine Exception.

Optional manuell im Browser prüfen:

1. `/search` — Liste ist initial befüllt, neue Fahrzeuge oben.
2. Neue Reparatur mit Bild + Kommentar — Kommentar erscheint unter Thumbnail.
3. Klick auf Thumbnail → Modal — Kommentar editierbar — Speichern → Caption updated ohne Reload.
4. Zwei Reparaturen am gleichen Tag — die später erstellte steht oben.

- [ ] **Step 19.7: Final Commit (falls Format-Anpassungen nötig waren)**

```bash
git add -A && git commit -m "chore: format pass after feature merge" || echo "nothing to commit"
```

---

## Notes for the implementing engineer

- **DRY:** Test-Helper (`_seed_vehicle`, `_jpeg_bytes`, etc.) bestehen in mehreren Testdateien. Bei Bedarf in ein gemeinsames `tests/_helpers.py` ziehen — aber nur, wenn Duplikation in dieser PR auf >3 Stellen geht.
- **YAGNI:** Keine zusätzlichen Features (Sortier-Optionen, Pagination, Auth, FTS-für-Comments). Spec ist Vertrag.
- **TDD:** Jeder Task führt zuerst einen failing Test ein. Implementieren erst danach.
- **Commits:** Pro Task ein Commit. Falls ein Task scheitert, NICHT amenden — neuer Commit "fix: ...".
- **Architekturgrenzen:** `rapidfuzz` lebt nur in `infrastructure/search/`. Application nutzt den `FuzzyMatcher`-Port.

Bei Unklarheit zwischen Plan und Spec: **Spec gewinnt** (`docs/superpowers/specs/2026-05-10-image-comments-sorting-vehicle-dropdown-design.md`).
