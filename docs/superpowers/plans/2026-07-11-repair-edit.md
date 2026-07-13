# Reparatur bearbeiten (Beschreibung + Foto-Upload) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine bestehende Reparatur bearbeitbar machen — Beschreibung anpassen (Datum unveränderlich) und neue Fotos über den bestehenden Upload-Flow hochladen.

**Architecture:** Neuer `UpdateRepairUseCase` (Application, ohne Index-Zugriff wie `CreateRepairUseCase`); eine eigene Edit-Seite in der Presentation (Route + Template + Detail-Link + Container-Wiring); ein Robustheits-Fix im Live-Watcher (`_handle_image` ordnet Bilder über die Reparatur-ULID in der Ordner-Sidecar zu statt über den aus der Beschreibung neu berechneten Ordner-Slug).

**Tech Stack:** Python 3.13, FastAPI + Jinja2, pytest, ULID, SQLite-Index über Live-Watcher (`watchdog`), Clean Architecture (domain/application/infrastructure/presentation).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-11-repair-edit-design.md`.
- TDD: kein Produktionscode ohne zuvor fehlschlagenden Test. Gates: `uv run pytest`, `uv run pyright`, `uv run ruff check .`.
- Line-length 110 (`ruff.toml`).
- Domain-Exceptions ohne `Error`-Suffix (DDD-Konvention).
- Bestehenden Mustern folgen: Routen wie `routes/vehicles.py` (edit_vehicle), Use-Cases wie `application/create_repair.py`, Templates wie `templates/edit_vehicle.html`.
- **Datum bleibt unveränderlich**; Reparatur-Ordner wird **nicht** umbenannt.
- `UpdateRepairUseCase` fasst den Index **nicht** an (Index-Konsistenz über den Watcher/Reindex, wie bei `CreateRepairUseCase`).
- Vehicle-URL-Key immer über `vehicle_url_key(vehicle)` kanonisieren; Reparatur/Fahrzeug-Zugehörigkeit prüfen.

---

### Task 1: `UpdateRepairUseCase` (Application)

**Files:**
- Create: `src/edelrep/application/update_repair.py`
- Test: `tests/application/test_update_repair.py`

**Interfaces:**
- Consumes: `RepairRepository.get(repair_id) -> Repair` (raises `RepairNotFound`), `RepairRepository.update(repair) -> None`; entity `Repair(id, vehicle_id, date, description, created_at)`.
- Produces: `UpdateRepairUseCase(repair_repo: RepairRepository)` with `execute(*, repair_id: ULID, description: str | None) -> Repair`. Task 2 (container) constructs it; the route calls `execute`.

- [ ] **Step 1: Write the failing tests**

Create `tests/application/test_update_repair.py`:

```python
from datetime import UTC, date, datetime

import pytest
from ulid import ULID

from edelrep.application.update_repair import UpdateRepairUseCase
from edelrep.domain.entities import Repair
from edelrep.domain.exceptions import RepairNotFound
from tests.application.fakes import InMemoryRepairRepo


def _seed_repair(repo: InMemoryRepairRepo) -> Repair:
    repair = Repair(
        id=ULID(),
        vehicle_id=ULID(),
        date=date(2026, 5, 3),
        description="alt",
        created_at=datetime(2026, 5, 3, tzinfo=UTC),
    )
    repo.save(repair)
    return repair


def test_update_repair_changes_description_and_keeps_identity() -> None:
    repo = InMemoryRepairRepo()
    original = _seed_repair(repo)

    updated = UpdateRepairUseCase(repo).execute(repair_id=original.id, description="neu")

    assert updated.description == "neu"
    assert updated.id == original.id
    assert updated.vehicle_id == original.vehicle_id
    assert updated.date == original.date
    assert updated.created_at == original.created_at
    assert repo.get(original.id).description == "neu"


def test_update_repair_blank_description_becomes_none() -> None:
    repo = InMemoryRepairRepo()
    original = _seed_repair(repo)

    updated = UpdateRepairUseCase(repo).execute(repair_id=original.id, description="   ")

    assert updated.description is None


def test_update_repair_unknown_id_raises() -> None:
    with pytest.raises(RepairNotFound):
        UpdateRepairUseCase(InMemoryRepairRepo()).execute(repair_id=ULID(), description="x")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/application/test_update_repair.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'edelrep.application.update_repair'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/edelrep/application/update_repair.py`:

```python
from ulid import ULID

from edelrep.domain.entities import Repair
from edelrep.domain.ports import RepairRepository


class UpdateRepairUseCase:
    """Update an existing repair's description. Date and identity are immutable.

    Mirrors CreateRepairUseCase: writes only through the repository. Index
    consistency is handled by the live watcher / full reindex.
    """

    def __init__(self, repair_repo: RepairRepository) -> None:
        self._repair_repo = repair_repo

    def execute(self, *, repair_id: ULID, description: str | None) -> Repair:
        existing = self._repair_repo.get(repair_id)
        normalised = (description.strip() if description else None) or None
        updated = Repair(
            id=existing.id,
            vehicle_id=existing.vehicle_id,
            date=existing.date,
            description=normalised,
            created_at=existing.created_at,
        )
        self._repair_repo.update(updated)
        return updated
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/application/test_update_repair.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/edelrep/application/update_repair.py tests/application/test_update_repair.py
git commit -m "feat(repair): UpdateRepairUseCase for editing the description"
```

---

### Task 2: Edit-Seite (Presentation: Container-Wiring, Route, Template, Detail-Link)

**Files:**
- Modify: `src/edelrep/presentation/container.py` (import + field + wiring)
- Modify: `src/edelrep/presentation/routes/repairs.py` (add GET + POST edit routes)
- Create: `src/edelrep/presentation/templates/edit_repair.html`
- Modify: `src/edelrep/presentation/templates/vehicle_detail.html` (Bearbeiten-Link pro Reparatur-Karte)
- Test: `tests/presentation/test_repairs.py` (append new tests)

**Interfaces:**
- Consumes: `UpdateRepairUseCase.execute(*, repair_id, description)` (Task 1); `container.repair_repo.get(rid) -> Repair`; `resolve_vehicle(vehicle_repo, key) -> Vehicle`; `vehicle_url_key(vehicle) -> str`.
- Produces: HTTP routes `GET /vehicles/{vehicle_key}/repairs/{repair_id}/edit` (renders form) and `POST /vehicles/{vehicle_key}/repairs/{repair_id}/edit` (updates → 303 redirect to `/vehicles/{canonical_key}`). Container field `update_repair: UpdateRepairUseCase`.

- [ ] **Step 1: Wire `UpdateRepairUseCase` into the container**

In `src/edelrep/presentation/container.py`:

Add the import next to the other application imports (near `from edelrep.application.update_image_comment import UpdateImageCommentUseCase`):

```python
from edelrep.application.update_repair import UpdateRepairUseCase
```

Add the dataclass field next to `create_repair: CreateRepairUseCase`:

```python
    update_repair: UpdateRepairUseCase
```

Add the wiring inside `Container(...)` in `build_container`, next to `create_repair=CreateRepairUseCase(vehicle_repo, repair_repo),`:

```python
        update_repair=UpdateRepairUseCase(repair_repo),
```

- [ ] **Step 2: Write the failing presentation tests**

Append to `tests/presentation/test_repairs.py`. Add these imports at the top of the file (`TestClient`, `ULID`, `Container` are already imported):

```python
from datetime import date

from edelrep.domain.entities import Vehicle
```

Then add the helper and tests:

```python
def _seed_vehicle_and_repair(container: Container) -> tuple[Vehicle, str]:
    vehicle = container.create_vehicle.execute(
        registration_number="12345", vin=None, description=None
    )
    repair = container.create_repair.execute(
        vehicle_id=vehicle.id, repair_date=date(2026, 5, 3), description="alt"
    )
    return vehicle, str(repair.id)


def test_edit_repair_form_shows_current_description(
    client: TestClient, container: Container
) -> None:
    _, repair_id = _seed_vehicle_and_repair(container)
    r = client.get(f"/vehicles/12345/repairs/{repair_id}/edit")
    assert r.status_code == 200
    assert "alt" in r.text


def test_edit_repair_updates_and_redirects(client: TestClient, container: Container) -> None:
    vehicle, repair_id = _seed_vehicle_and_repair(container)
    r = client.post(
        f"/vehicles/12345/repairs/{repair_id}/edit",
        data={"description": "neu"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/vehicles/12345"
    repairs = list(container.list_repairs.execute(vehicle.id))
    assert repairs[0].description == "neu"


def test_edit_repair_missing_vehicle_returns_404(client: TestClient) -> None:
    r = client.get("/vehicles/99999/repairs/01J9TGZP6X2K0V3W7Y8Z4QABCD/edit")
    assert r.status_code == 404


def test_edit_repair_unknown_repair_returns_404(
    client: TestClient, container: Container
) -> None:
    container.create_vehicle.execute(registration_number="12345", vin=None, description=None)
    r = client.get("/vehicles/12345/repairs/01J9TGZP6X2K0V3W7Y8Z4QABCD/edit")
    assert r.status_code == 404


def test_edit_repair_invalid_repair_id_returns_404(
    client: TestClient, container: Container
) -> None:
    container.create_vehicle.execute(registration_number="12345", vin=None, description=None)
    r = client.get("/vehicles/12345/repairs/not-a-ulid/edit")
    assert r.status_code == 404


def test_edit_repair_wrong_vehicle_returns_404(
    client: TestClient, container: Container
) -> None:
    _, repair_id = _seed_vehicle_and_repair(container)
    container.create_vehicle.execute(registration_number="67890", vin=None, description=None)
    # Repair belongs to vehicle 12345, requested under 67890.
    r = client.get(f"/vehicles/67890/repairs/{repair_id}/edit")
    assert r.status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/presentation/test_repairs.py -k edit_repair -q`
Expected: FAIL — GET/POST return 404 (routes not registered) so the 200/303 assertions fail.

- [ ] **Step 4: Add the edit routes**

In `src/edelrep/presentation/routes/repairs.py`:

Update the imports at the top:

```python
from datetime import date as _date

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from ulid import ULID

from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.exceptions import RepairNotFound, VehicleNotFound
from edelrep.presentation.container import Container
from edelrep.presentation.dependencies import ContainerDep
from edelrep.presentation.vehicle_lookup import resolve_vehicle, vehicle_url_key
```

`Container` is imported for the helper's type annotation only; `container.py` does not import the routes, so there is no import cycle.

Append these two routes to the end of the file:

```python
def _resolve_repair(
    container: Container, vehicle_key: str, repair_id: str
) -> tuple[Vehicle, Repair]:
    """Return (vehicle, repair) or raise HTTPException(404)."""
    try:
        vehicle = resolve_vehicle(container.vehicle_repo, vehicle_key)
    except VehicleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        rid = ULID.from_str(repair_id)
        repair = container.repair_repo.get(rid)
    except (ValueError, RepairNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if repair.vehicle_id != vehicle.id:
        raise HTTPException(status_code=404, detail="repair does not belong to vehicle")
    return vehicle, repair


@router.get(
    "/vehicles/{vehicle_key}/repairs/{repair_id}/edit",
    response_class=HTMLResponse,
)
def edit_repair_form(
    request: Request,
    container: ContainerDep,
    vehicle_key: str,
    repair_id: str,
) -> HTMLResponse:
    vehicle, repair = _resolve_repair(container, vehicle_key, repair_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "edit_repair.html",
        {
            "vehicle_key": vehicle_url_key(vehicle),
            "repair": repair,
            "form": {"description": repair.description or ""},
        },
    )


@router.post("/vehicles/{vehicle_key}/repairs/{repair_id}/edit", response_model=None)
def edit_repair(
    request: Request,
    container: ContainerDep,
    vehicle_key: str,
    repair_id: str,
    description: str = Form(""),
) -> RedirectResponse:
    vehicle, repair = _resolve_repair(container, vehicle_key, repair_id)
    container.update_repair.execute(repair_id=repair.id, description=description.strip() or None)
    return RedirectResponse(url=f"/vehicles/{vehicle_url_key(vehicle)}", status_code=303)
```

Note: the existing `create_repair` route already uses `_date` (kept in the import block above). Keep the existing `new_repair_form` / `create_repair` functions unchanged.

- [ ] **Step 5: Create the edit template**

Create `src/edelrep/presentation/templates/edit_repair.html`:

```html
{% extends "base.html" %}
{% block title %}Reparatur bearbeiten{% endblock %}
{% block content %}
<h1 class="text-2xl font-bold mb-6 tracking-tight">Reparatur bearbeiten</h1>
<form method="post" action="/vehicles/{{ vehicle_key }}/repairs/{{ repair.id }}/edit"
      class="bg-white border border-stone-200 rounded-xl shadow-sm p-6 space-y-5">
  <div>
    <span class="block text-sm font-medium text-stone-700 mb-1.5">Datum</span>
    <p class="font-mono text-stone-800">{{ repair.date.isoformat() }}</p>
  </div>
  <div>
    <label for="description" class="block text-sm font-medium text-stone-700 mb-1.5">Beschreibung <span class="text-stone-500 font-normal">(optional)</span></label>
    <textarea id="description" name="description" rows="3"
              class="w-full px-3 py-2.5 bg-white border border-stone-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-[#b59775] focus:border-[#b59775] transition-shadow">{{ form.description }}</textarea>
  </div>
  <div class="flex items-center justify-between gap-3">
    <a href="/vehicles/{{ vehicle_key }}"
       class="text-stone-600 hover:text-stone-900 text-sm font-medium">Abbrechen</a>
    <button type="submit"
            class="bg-[#b59775] hover:bg-[#ac8a64] text-white px-6 py-2.5 rounded-lg font-medium shadow-sm transition-colors">
      Speichern
    </button>
  </div>
</form>
<a href="/vehicles/{{ vehicle_key }}/repairs/{{ repair.id }}/upload"
   class="inline-block mt-4 text-sm text-[#ac8a64] hover:text-[#8a6f4f] font-medium">Fotos hochladen</a>
{% endblock %}
```

- [ ] **Step 6: Run the edit tests to verify they pass**

Run: `uv run pytest tests/presentation/test_repairs.py -k edit_repair -q`
Expected: PASS (5 passed).

- [ ] **Step 7: Add the "Bearbeiten" link on the vehicle detail page (failing test first)**

Append to `tests/presentation/test_repairs.py`:

```python
def test_vehicle_detail_shows_edit_link_per_repair(
    client: TestClient, container: Container
) -> None:
    _, repair_id = _seed_vehicle_and_repair(container)
    r = client.get("/vehicles/12345")
    assert f"/vehicles/12345/repairs/{repair_id}/edit" in r.text
```

Run: `uv run pytest tests/presentation/test_repairs.py -k edit_link -q`
Expected: FAIL — the edit URL is not present in the detail HTML.

- [ ] **Step 8: Add the link in `vehicle_detail.html`**

In `src/edelrep/presentation/templates/vehicle_detail.html`, replace the existing "Bilder hochladen" anchor block:

```html
    <a href="/vehicles/{{ vehicle_key }}/repairs/{{ r.id }}/upload"
       class="inline-flex items-center gap-1.5 text-sm text-[#ac8a64] hover:text-[#8a6f4f] font-medium mt-3 transition-colors">
      {{ icon("image-plus", "w-4 h-4") }} Bilder hochladen
    </a>
```

with:

```html
    <div class="mt-3 flex items-center gap-4">
      <a href="/vehicles/{{ vehicle_key }}/repairs/{{ r.id }}/edit"
         class="text-sm text-[#ac8a64] hover:text-[#8a6f4f] font-medium transition-colors">
        Bearbeiten
      </a>
      <a href="/vehicles/{{ vehicle_key }}/repairs/{{ r.id }}/upload"
         class="inline-flex items-center gap-1.5 text-sm text-[#ac8a64] hover:text-[#8a6f4f] font-medium transition-colors">
        {{ icon("image-plus", "w-4 h-4") }} Bilder hochladen
      </a>
    </div>
```

- [ ] **Step 9: Run the whole presentation repair suite + gates**

Run: `uv run pytest tests/presentation/test_repairs.py -q && uv run pyright src/edelrep/presentation/routes/repairs.py src/edelrep/presentation/container.py && uv run ruff check src/edelrep/presentation/routes/repairs.py src/edelrep/presentation/container.py src/edelrep/application/update_repair.py`
Expected: all pytest PASS; pyright 0 errors; ruff no new errors.

- [ ] **Step 10: Commit**

```bash
git add src/edelrep/presentation/container.py src/edelrep/presentation/routes/repairs.py src/edelrep/presentation/templates/edit_repair.html src/edelrep/presentation/templates/vehicle_detail.html tests/presentation/test_repairs.py
git commit -m "feat(repair): edit page for a repair's description with photo-upload link"
```

---

### Task 3: Live-Index `_handle_image` über Sidecar-ID auflösen (Bugfix)

**Files:**
- Modify: `src/edelrep/infrastructure/watcher/live_index.py` (`_handle_image`; remove now-unused `repair_dir_name` import)
- Test: `tests/infrastructure/watcher/test_live_index_unit.py` (append regression test)

**Interfaces:**
- Consumes: `read_sidecar(path: Path) -> dict` from `edelrep.infrastructure.filesystem.sidecar` (returns the repair dict incl. `"id"`, schema envelope stripped; raises `SidecarSchemaError`); `SidecarSchemaError` from `edelrep.domain.exceptions`.
- Produces: `_handle_image` matches an uploaded image to its repair by the repair-ULID stored in the folder's `_repair.json`, independent of whether the folder slug still matches the (possibly edited) description.

- [ ] **Step 1: Write the failing regression test**

Append to `tests/infrastructure/watcher/test_live_index_unit.py`. Add these imports at the top of the file if missing:

```python
from edelrep.infrastructure.filesystem.sidecar import write_sidecar
```

Add a fixed repair ULID constant near the other IDs:

```python
REPAIR_ID = ULID.from_str("01J9TGZP6X2K0V3W7Y8Z4QREPA")
REPAIR_ID_STR = str(REPAIR_ID)
```

Add the test:

```python
def test_handle_image_matches_repair_by_sidecar_after_description_edit(
    live: LiveIndex, tmp_path: Path
) -> None:
    """After a description edit the folder slug diverges; images must still match
    their repair via the repair-ULID in the folder's _repair.json sidecar."""
    storage_root = tmp_path / "store"
    # Folder name reflects the ORIGINAL slug; the repair's description was since edited.
    dir_name = "2026-04-15__old-slug"
    sidecar = storage_root / VEHICLE_ID_STR / dir_name / "_repair.json"
    sidecar.parent.mkdir(parents=True)
    write_sidecar(
        sidecar,
        {
            "id": REPAIR_ID_STR,
            "date": "2026-04-15",
            "description": "neue beschreibung",
            "created_at": "2026-05-03T00:00:00+00:00",
        },
    )
    live._vehicle_repo.save(  # type: ignore[union-attr]
        Vehicle(
            id=VEHICLE_ID,
            registration_number="12345",
            vin="W",
            description="x",
            created_at=datetime(2026, 5, 3, tzinfo=UTC),
        )
    )
    live._repair_repo.save(  # type: ignore[union-attr]
        Repair(
            id=REPAIR_ID,
            vehicle_id=VEHICLE_ID,
            date=date(2026, 4, 15),
            description="neue beschreibung",
            created_at=datetime(2026, 5, 3, tzinfo=UTC),
        )
    )
    image = Image(
        id=ULID(),
        repair_id=REPAIR_ID,
        storage_key="placeholder",
        thumbnail_key=None,
        filename="0001.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime(2026, 5, 3, tzinfo=UTC),
        captured_at=None,
    )
    live._image_repo.save(image, raw_bytes=b"\xff\xd8\xff\xd9")  # type: ignore[union-attr]

    live._apply_batch(
        {f"{VEHICLE_ID_STR}/{dir_name}/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg"}
    )

    _proj(live).upsert_image.assert_called()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/infrastructure/watcher/test_live_index_unit.py -k matches_repair_by_sidecar -q`
Expected: FAIL — `upsert_image` not called, because the old `_handle_image` recomputes `repair_dir_name(date, "neue beschreibung")` = `2026-04-15__neue-beschreibung`, which does not equal the folder `2026-04-15__old-slug`.

- [ ] **Step 3: Fix `_handle_image`**

In `src/edelrep/infrastructure/watcher/live_index.py`:

Update the imports. Replace:

```python
from edelrep.domain.exceptions import RepairNotFound, VehicleNotFound
```

with:

```python
from edelrep.domain.exceptions import RepairNotFound, SidecarSchemaError, VehicleNotFound
```

Add near the other infrastructure imports:

```python
from edelrep.infrastructure.filesystem.sidecar import read_sidecar
```

Remove the now-unused import (it is only referenced by the old `_handle_image`):

```python
from edelrep.infrastructure.filesystem.layout import repair_dir_name
```

Replace the whole `_handle_image` method with:

```python
    def _handle_image(self, key: str) -> None:
        vehicle_str, dir_name, _ = key.split("/", 2)
        try:
            vid = ULID.from_str(vehicle_str)
            vehicle = self._vehicle_repo.get(vid)
        except (ValueError, VehicleNotFound):
            return
        sidecar_path = self._storage_root / vehicle_str / dir_name / "_repair.json"
        if not sidecar_path.is_file():
            return
        try:
            repair_id = ULID.from_str(str(read_sidecar(sidecar_path)["id"]))
        except (ValueError, KeyError, OSError, SidecarSchemaError):
            return
        for repair in self._repair_repo.list_for_vehicle(vehicle.id):
            if repair.id != repair_id:
                continue
            try:
                images = list(self._image_repo.list_for_repair(repair.id))
            except RepairNotFound:
                return
            for image in images:
                self._projector.upsert_image(image)
            return
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/infrastructure/watcher/test_live_index_unit.py -k matches_repair_by_sidecar -q`
Expected: PASS.

- [ ] **Step 5: Run the full watcher suite + gates**

Run: `uv run pytest tests/infrastructure/watcher/ -q && uv run pyright src/edelrep/infrastructure/watcher/live_index.py && uv run ruff check src/edelrep/infrastructure/watcher/live_index.py`
Expected: all PASS; pyright 0 errors; ruff no new errors (confirms `repair_dir_name` import removal left nothing unused).

- [ ] **Step 6: Commit**

```bash
git add src/edelrep/infrastructure/watcher/live_index.py tests/infrastructure/watcher/test_live_index_unit.py
git commit -m "fix(index): match uploaded images to repair by sidecar id, not slug"
```

---

### Final verification

- [ ] **Run the whole suite + all gates**

Run: `uv run pytest -q && uv run pyright && uv run ruff check .`
Expected: full suite PASS; pyright 0 errors; ruff shows no *new* errors introduced by these tasks (pre-existing repo-wide findings are out of scope).

- [ ] **Drive the feature once (optional but recommended)**

Use the `verify` skill or start the app (`uv run edelrep serve --storage-root .\\bilder --index-path index.db`), open a vehicle with a repair, click "Bearbeiten", change the description, save, and confirm the detail page shows the new description; then upload a photo and confirm it appears.
