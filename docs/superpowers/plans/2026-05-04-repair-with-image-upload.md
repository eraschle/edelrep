# Reparatur-Anlage mit Multi-Image-Upload — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Beim Anlegen einer Reparatur können Beschreibung, Datum und ein oder mehrere Bilder (von Laptop, iPhone, Android — Kamera oder Galerie) im selben Formular eingereicht werden, mit Pro-Bild-Status während des Uploads.

**Architecture:** Bestehende Use-Cases `CreateRepair` und `UploadImage` bleiben unverändert. Die zwei betroffenen Endpunkte erhalten eine zusätzliche JSON-Antwort-Variante (Content-Negotiation per `Accept`-Header). Ein wiederverwendbares Jinja2-Macro `_image_picker.html` kapselt Datei-Auswahl, Vorschau, Validierung und Upload-Logik (vanilla JS). Ohne JavaScript funktioniert der klassische Zwei-Schritt-Flow weiter (Progressive Enhancement).

**Tech Stack:** FastAPI, Jinja2, Tailwind (CDN), vanilla JS, pytest + FastAPI TestClient (kein Playwright in V1).

**Spec:** `docs/superpowers/specs/2026-05-04-repair-with-image-upload-design.md`

---

## File Structure

**Neue Dateien:**

- `src/edelrep/presentation/templates/_image_picker.html` — Jinja2-Macro `image_picker(name, max_size_mb=25)` mit HTML-Struktur, Buttons, Vorschau-Container, Template-Element und IIFE-JS für die Picker-Verwaltung (Datei-Auswahl, Validierung, Vorschau, Status-Updates). Keine Upload-Logik — die liegt im Submit-Handler der jeweiligen Seite.

**Geänderte Dateien:**

- `src/edelrep/presentation/routes/repairs.py` — `create_repair`-Handler bekommt Content-Negotiation: bei `Accept: application/json` antwortet er mit `201 {"repair_id", "vehicle_url"}`, Validierungs-/Not-Found-Fehler als `{"error": "..."}` mit passendem Status. Sonst (HTML-Form-Submit) unverändertes 303-Redirect-Verhalten.
- `src/edelrep/presentation/routes/images.py` — `upload_image`-Handler analog: `Accept: application/json` → `201 {"image_id"}` oder Error-JSON. Sonst 303 Redirect.
- `src/edelrep/presentation/templates/new_repair.html` — bindet `_image_picker.html` ein, fügt Submit-Orchestrierungs-JS hinzu (Repair-POST → Bild-POST-Schleife → Redirect).
- `src/edelrep/presentation/templates/upload_image.html` — bindet `_image_picker.html` ein, Submit-JS macht nur die Bild-POST-Schleife (kein Repair-Create).
- `tests/presentation/test_repairs.py` — 3 neue Tests für JSON-Variante des Repair-Endpoints.
- `tests/presentation/test_images.py` — 3 neue Tests für JSON-Variante des Image-Endpoints.

**Bewusst weggelassen (Spec-Out-of-Scope ggü. Plan):**

- Playwright-E2E-Tests werden **nicht** Teil von V1 — die Spec hatte das vorgesehen, aber das Projekt nutzt durchgehend FastAPI TestClient ohne Playwright-Setup. Ein Playwright-Setup wäre eine eigene Plan-Einheit. Die JS-Submit-Orchestrierung wird per manuellem Test-Pfad (Task 6) abgedeckt; Server-Verträge sind durch TestClient-Tests vollständig geprüft.

---

## Task 1: Server — JSON-Variante für `POST /vehicles/{reg}/repairs`

**Files:**
- Modify: `src/edelrep/presentation/routes/repairs.py`
- Test: `tests/presentation/test_repairs.py`

- [ ] **Step 1.1: Write failing test for happy-path JSON response**

In `tests/presentation/test_repairs.py` am Ende anhängen:

```python
def test_create_repair_with_json_accept_returns_201_and_repair_id(
    client: TestClient, container: Container
) -> None:
    _seed_vehicle(container)
    r = client.post(
        "/vehicles/12345/repairs",
        data={"description": "brakes", "date": "2026-05-03"},
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    assert r.status_code == 201
    body = r.json()
    assert "repair_id" in body
    assert body["vehicle_url"] == "/vehicles/12345"
    # repair_id must be parseable as a ULID.
    from ulid import ULID
    ULID.from_str(body["repair_id"])


def test_create_repair_with_json_accept_invalid_date_returns_400_json(
    client: TestClient, container: Container
) -> None:
    _seed_vehicle(container)
    r = client.post(
        "/vehicles/12345/repairs",
        data={"description": "brakes", "date": "not-a-date"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 400
    assert "error" in r.json()


def test_create_repair_with_json_accept_missing_vehicle_returns_404_json(
    client: TestClient,
) -> None:
    r = client.post(
        "/vehicles/99999/repairs",
        data={"description": "brakes", "date": "2026-05-03"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 404
    assert "error" in r.json()
```

- [ ] **Step 1.2: Run tests — verify they fail**

Run: `uv run pytest tests/presentation/test_repairs.py -v -k "json_accept"`
Expected: 3 failures (returns 303 instead of 201/400/404 with JSON, oder body ist HTML).

- [ ] **Step 1.3: Add JSON support to the route**

Replace the entire `create_repair` function in `src/edelrep/presentation/routes/repairs.py` with:

```python
@router.post("/vehicles/{registration_number}/repairs", response_model=None)
def create_repair(
    request: Request,
    container: ContainerDep,
    registration_number: str,
    description: str = Form(...),
    date: str = Form(...),
) -> HTMLResponse | RedirectResponse | JSONResponse:
    wants_json = "application/json" in request.headers.get("accept", "")
    try:
        vehicle_id = VehicleId(registration_number)
    except InvalidVehicleId as exc:
        if wants_json:
            return JSONResponse({"error": str(exc)}, status_code=404)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        parsed_date = _date.fromisoformat(date)
    except ValueError as exc:
        if wants_json:
            return JSONResponse({"error": str(exc)}, status_code=400)
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "new_repair.html",
            {
                "registration_number": registration_number,
                "errors": {"date": str(exc)},
            },
            status_code=400,
        )
    try:
        repair = container.create_repair.execute(
            vehicle_id=vehicle_id,
            repair_date=parsed_date,
            description=description,
        )
    except VehicleNotFound as exc:
        if wants_json:
            return JSONResponse({"error": str(exc)}, status_code=404)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if wants_json:
        return JSONResponse(
            {
                "repair_id": str(repair.id),
                "vehicle_url": f"/vehicles/{registration_number}",
            },
            status_code=201,
        )
    return RedirectResponse(
        url=f"/vehicles/{registration_number}",
        status_code=303,
    )
```

Add to the imports at the top of the file:

```python
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
```

(Replace the existing `from fastapi.responses import HTMLResponse, RedirectResponse` line.)

- [ ] **Step 1.4: Run all repair tests — verify both old and new pass**

Run: `uv run pytest tests/presentation/test_repairs.py -v`
Expected: alle Tests grün (alte HTML-Tests UND die 3 neuen JSON-Tests).

- [ ] **Step 1.5: Commit**

```bash
git add src/edelrep/presentation/routes/repairs.py tests/presentation/test_repairs.py
git commit -m "$(cat <<'EOF'
feat(presentation): JSON-Antwort-Variante für POST /repairs

Content-Negotiation per Accept-Header: bei application/json antwortet
der Endpunkt mit 201 + {repair_id, vehicle_url} statt 303-Redirect.
Vorbereitung für JS-gesteuerten Multi-Image-Upload.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Server — JSON-Variante für `POST /vehicles/{reg}/repairs/{id}/images`

**Files:**
- Modify: `src/edelrep/presentation/routes/images.py`
- Test: `tests/presentation/test_images.py`

- [ ] **Step 2.1: Write failing tests**

In `tests/presentation/test_images.py` am Ende anhängen:

```python
def test_upload_image_with_json_accept_returns_201_and_image_id(
    client: TestClient, container: Container
) -> None:
    repair_id = _seed_repair(container)
    jpeg = _make_jpeg()
    r = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("photo.jpg", jpeg, "image/jpeg")},
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    assert r.status_code == 201
    body = r.json()
    assert "image_id" in body
    ULID.from_str(body["image_id"])


def test_upload_non_image_with_json_accept_returns_422_json(
    client: TestClient, container: Container
) -> None:
    repair_id = _seed_repair(container)
    r = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("photo.jpg", b"this is not an image", "image/jpeg")},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 422
    assert "error" in r.json()


def test_upload_image_missing_repair_with_json_accept_returns_404_json(
    client: TestClient, container: Container
) -> None:
    container.create_vehicle.execute(registration_number="12345", vin=None, description=None)
    jpeg = _make_jpeg()
    r = client.post(
        "/vehicles/12345/repairs/01J9TGZP6X2K0V3W7Y8Z4QABCD/images",
        files={"image": ("photo.jpg", jpeg, "image/jpeg")},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 404
    assert "error" in r.json()
```

- [ ] **Step 2.2: Run tests — verify they fail**

Run: `uv run pytest tests/presentation/test_images.py -v -k "json_accept"`
Expected: 3 failures.

- [ ] **Step 2.3: Add JSON support to the route**

Replace the `upload_image` function in `src/edelrep/presentation/routes/images.py` with:

```python
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
        )
    except RepairNotFound as exc:
        if wants_json:
            return JSONResponse({"error": str(exc)}, status_code=404)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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
```

Update imports at the top of the file. Replace:

```python
from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
```

with:

```python
from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
```

- [ ] **Step 2.4: Run all image tests**

Run: `uv run pytest tests/presentation/test_images.py -v`
Expected: alle Tests grün.

- [ ] **Step 2.5: Commit**

```bash
git add src/edelrep/presentation/routes/images.py tests/presentation/test_images.py
git commit -m "$(cat <<'EOF'
feat(presentation): JSON-Antwort-Variante für POST /images

Content-Negotiation per Accept-Header: bei application/json antwortet
der Endpunkt mit 201 + {image_id} (oder 4xx + {error}) statt 303-Redirect.
Vorbereitung für sequenziellen JS-Upload mit Pro-Bild-Status.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Image-Picker-Macro (HTML-Struktur + Datei-Auswahl-JS)

Diese Komponente kapselt: zwei Buttons (Foto/Galerie), versteckte File-Inputs, Vorschau-Container, `<template>` für Eintrag-Klone, plus IIFE-JS für Hinzufügen/Entfernen/Validieren von Dateien. Die **Upload-Logik** lebt nicht hier — sie wird vom Submit-Handler der jeweiligen Seite (Task 4 + 5) gebaut, indem über die DOM-API `picker.getFiles()` iteriert und der Status pro Eintrag aktualisiert wird.

**Files:**
- Create: `src/edelrep/presentation/templates/_image_picker.html`

- [ ] **Step 3.1: Create the macro file**

Erstelle `src/edelrep/presentation/templates/_image_picker.html` mit folgendem Inhalt:

```jinja
{% macro image_picker(name="image_picker", max_size_mb=25) %}
<div class="image-picker space-y-3"
     data-image-picker
     data-name="{{ name }}"
     data-max-size-bytes="{{ max_size_mb * 1024 * 1024 }}">

  <input type="file" multiple accept="image/*"
         data-picker-input="gallery" hidden>
  <input type="file" accept="image/*" capture="environment"
         data-picker-input="camera" hidden>

  <div class="flex gap-3">
    <button type="button" data-picker-trigger="camera"
            class="flex-1 bg-slate-200 hover:bg-slate-300 text-slate-900 px-4 py-3 rounded font-medium">
      📷 Foto aufnehmen
    </button>
    <button type="button" data-picker-trigger="gallery"
            class="flex-1 bg-slate-200 hover:bg-slate-300 text-slate-900 px-4 py-3 rounded font-medium">
      📁 Bilder auswählen
    </button>
  </div>

  <p data-picker-hint class="text-sm text-slate-500" hidden></p>

  <ul data-picker-list class="space-y-2"></ul>

  <template data-picker-entry-template>
    <li class="flex items-center gap-3 bg-white border rounded p-2"
        data-entry>
      <img data-entry-thumb alt=""
           class="h-16 w-16 object-cover border rounded bg-slate-100">
      <div class="flex-1 min-w-0">
        <p data-entry-filename class="font-medium truncate"></p>
        <p data-entry-meta class="text-xs text-slate-500"></p>
        <p data-entry-status class="text-xs"></p>
      </div>
      <button type="button" data-entry-retry hidden
              class="text-sm text-blue-600 hover:underline">Erneut</button>
      <button type="button" data-entry-remove
              class="text-slate-400 hover:text-red-600 text-xl px-2"
              aria-label="Entfernen">×</button>
    </li>
  </template>
</div>

<script>
(function () {
  // Initialise every uninitialised picker on the page.
  document.querySelectorAll('[data-image-picker]:not([data-initialised])').forEach(initPicker);

  function initPicker(root) {
    root.dataset.initialised = '1';
    const maxSize = Number(root.dataset.maxSizeBytes);
    const galleryInput = root.querySelector('[data-picker-input="gallery"]');
    const cameraInput = root.querySelector('[data-picker-input="camera"]');
    const list = root.querySelector('[data-picker-list]');
    const tpl = root.querySelector('[data-picker-entry-template]');
    const hint = root.querySelector('[data-picker-hint]');
    const entries = []; // {id, file, status, el, statusEl, retryBtn}
    let nextId = 1;

    root.querySelector('[data-picker-trigger="camera"]').addEventListener('click', () => cameraInput.click());
    root.querySelector('[data-picker-trigger="gallery"]').addEventListener('click', () => galleryInput.click());
    galleryInput.addEventListener('change', () => {
      addFiles(Array.from(galleryInput.files || []));
      galleryInput.value = '';
    });
    cameraInput.addEventListener('change', () => {
      addFiles(Array.from(cameraInput.files || []));
      cameraInput.value = '';
    });

    function addFiles(files) {
      let added = false;
      for (const file of files) {
        const result = addFile(file);
        if (result === 'ok') added = true;
      }
      if (added) emitChange();
    }

    function addFile(file) {
      // 1. MIME check
      if (!file.type.startsWith('image/')) {
        renderInvalidEntry(file, 'Kein Bildformat');
        return 'invalid';
      }
      // 2. Size check
      if (file.size > maxSize) {
        const mb = (file.size / (1024 * 1024)).toFixed(1);
        const maxMb = Math.round(maxSize / (1024 * 1024));
        renderInvalidEntry(file, `Zu gross (${mb} MB, max ${maxMb})`);
        return 'invalid';
      }
      // 3. Duplicate check
      if (entries.some(e => e.file.name === file.name && e.file.size === file.size)) {
        showHint(`"${file.name}" ist bereits ausgewählt.`);
        return 'duplicate';
      }
      const id = nextId++;
      const el = renderEntry(file, id);
      entries.push({ id, file, status: 'pending', el,
                     statusEl: el.querySelector('[data-entry-status]'),
                     retryBtn: el.querySelector('[data-entry-retry]') });
      return 'ok';
    }

    function renderEntry(file, id) {
      const li = tpl.content.firstElementChild.cloneNode(true);
      li.dataset.entryId = String(id);
      li.querySelector('[data-entry-thumb]').src = URL.createObjectURL(file);
      li.querySelector('[data-entry-filename]').textContent = file.name;
      li.querySelector('[data-entry-meta]').textContent = formatBytes(file.size);
      li.querySelector('[data-entry-status]').textContent = '🕐 wartet';
      li.querySelector('[data-entry-remove]').addEventListener('click', () => removeEntry(id));
      list.appendChild(li);
      return li;
    }

    function renderInvalidEntry(file, message) {
      const li = tpl.content.firstElementChild.cloneNode(true);
      li.querySelector('[data-entry-thumb]').alt = '';
      const thumb = li.querySelector('[data-entry-thumb]');
      if (file.type.startsWith('image/')) {
        thumb.src = URL.createObjectURL(file);
      } else {
        thumb.classList.add('opacity-30');
      }
      li.querySelector('[data-entry-filename]').textContent = file.name;
      li.querySelector('[data-entry-meta]').textContent = formatBytes(file.size);
      const statusEl = li.querySelector('[data-entry-status]');
      statusEl.textContent = `❌ ${message}`;
      statusEl.classList.add('text-red-600');
      li.querySelector('[data-entry-remove]').addEventListener('click', () => li.remove());
      list.appendChild(li);
    }

    function removeEntry(id) {
      const idx = entries.findIndex(e => e.id === id);
      if (idx === -1) return;
      entries[idx].el.remove();
      entries.splice(idx, 1);
      emitChange();
    }

    function showHint(text) {
      hint.textContent = text;
      hint.hidden = false;
      setTimeout(() => { hint.hidden = true; }, 3000);
    }

    function formatBytes(n) {
      if (n < 1024) return `${n} B`;
      if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
      return `${(n / (1024 * 1024)).toFixed(1)} MB`;
    }

    function emitChange() {
      root.dispatchEvent(new CustomEvent('picker:change', {
        detail: { count: entries.length },
        bubbles: true,
      }));
    }

    // Public API exposed on the root element.
    root.pickerApi = {
      getEntries: () => entries.slice(),
      setStatus(id, status, message) {
        const e = entries.find(x => x.id === id);
        if (!e) return;
        e.status = status;
        const map = {
          uploading: { text: '🔄 lädt hoch…', cls: 'text-slate-600' },
          ok:        { text: '✅ hochgeladen', cls: 'text-green-700' },
          error:     { text: `❌ Fehler${message ? ': ' + message : ''}`, cls: 'text-red-600' },
          pending:   { text: '🕐 wartet', cls: 'text-slate-600' },
        };
        const m = map[status];
        e.statusEl.textContent = m.text;
        e.statusEl.className = 'text-xs ' + m.cls;
        e.retryBtn.hidden = (status !== 'error');
      },
      onRetry(id, handler) {
        const e = entries.find(x => x.id === id);
        if (!e) return;
        e.retryBtn.addEventListener('click', () => handler(e));
      },
    };
  }
})();
</script>
{% endmacro %}
```

- [ ] **Step 3.2: Smoke-test the macro renders without import errors**

Smoke-test: dass das Macro überhaupt ohne Jinja-Syntax-Fehler in einer Test-View renderbar ist (separater Test-Endpunkt nicht nötig — wir testen das Verhalten, indem in Task 4 die `new_repair.html`-View es einbindet, und die bestehenden Render-Tests auf `/repairs/new` weiterhin grün bleiben). Reine Syntax-Prüfung jetzt:

Run: `uv run python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('src/edelrep/presentation/templates')); env.get_template('_image_picker.html')"`
Expected: kein Fehler (kein Output, Exit 0).

- [ ] **Step 3.3: Commit**

```bash
git add src/edelrep/presentation/templates/_image_picker.html
git commit -m "$(cat <<'EOF'
feat(ui): wiederverwendbares Image-Picker-Macro

Jinja2-Macro mit zwei Buttons (Foto/Galerie via capture=environment),
versteckten File-Inputs, Vorschau-Liste mit Thumbnails, Validierung
(Typ/Grösse/Duplikat) und JS-API (pickerApi.setStatus/onRetry) für die
Upload-Orchestrierung im Submit-Handler der jeweiligen Seite.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `new_repair.html` — Macro einbinden + Submit-Orchestrierung

**Files:**
- Modify: `src/edelrep/presentation/templates/new_repair.html`

- [ ] **Step 4.1: Replace the template content**

Ersetze den **gesamten** Inhalt von `src/edelrep/presentation/templates/new_repair.html` mit:

```jinja
{% extends "base.html" %}
{% from "_image_picker.html" import image_picker %}
{% block title %}Neue Reparatur{% endblock %}
{% block content %}
<h1 class="text-2xl font-bold mb-4">Neue Reparatur für {{ registration_number }}</h1>

<noscript>
  <p class="bg-yellow-100 border border-yellow-300 text-yellow-900 p-3 rounded mb-4 text-sm">
    Ohne JavaScript kannst du die Reparatur anlegen und Bilder anschliessend
    auf der Fahrzeug-Detailseite über "Bilder hochladen" ergänzen.
  </p>
</noscript>

<form id="repair-form" method="post"
      action="/vehicles/{{ registration_number }}/repairs"
      class="space-y-5">
  <div>
    <label for="description" class="block text-sm font-medium">Beschreibung</label>
    <input type="text" id="description" name="description" required
           class="w-full p-3 border rounded">
  </div>
  <div>
    <label for="date" class="block text-sm font-medium">Datum</label>
    <input type="date" id="date" name="date" required
           class="w-full p-3 border rounded">
    {% if errors.date %}
      <p class="text-red-600 text-sm">{{ errors.date }}</p>
    {% endif %}
  </div>

  <div>
    <p class="block text-sm font-medium mb-2">Bilder (mind. 1)</p>
    {{ image_picker(name="repair_images") }}
  </div>

  <div id="repair-form-error" class="text-red-600 text-sm" hidden></div>
  <div id="repair-form-banner" class="bg-yellow-100 border border-yellow-300 text-yellow-900 p-3 rounded text-sm" hidden></div>

  <button type="submit" id="repair-submit"
          class="bg-blue-600 hover:bg-blue-700 disabled:bg-slate-400 text-white px-6 py-3 rounded font-semibold"
          disabled>
    Anlegen
  </button>
</form>

<script>
(function () {
  const form = document.getElementById('repair-form');
  const desc = document.getElementById('description');
  const dateEl = document.getElementById('date');
  const submit = document.getElementById('repair-submit');
  const errorBox = document.getElementById('repair-form-error');
  const banner = document.getElementById('repair-form-banner');
  const picker = form.querySelector('[data-image-picker]');

  function validImageCount() {
    if (!picker.pickerApi) return 0;
    return picker.pickerApi.getEntries().length;
  }

  function refreshSubmit() {
    const ok = desc.value.trim() && dateEl.value && validImageCount() > 0;
    submit.disabled = !ok;
  }

  desc.addEventListener('input', refreshSubmit);
  dateEl.addEventListener('input', refreshSubmit);
  picker.addEventListener('picker:change', refreshSubmit);

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    submit.disabled = true;
    submit.textContent = 'Lade hoch…';
    errorBox.hidden = true;
    banner.hidden = true;

    // 1. Create the repair.
    let repairResp;
    try {
      const fd = new FormData();
      fd.set('description', desc.value);
      fd.set('date', dateEl.value);
      repairResp = await fetch(form.action, {
        method: 'POST',
        headers: { 'Accept': 'application/json' },
        body: fd,
      });
    } catch (err) {
      showError('Netzwerkfehler beim Anlegen der Reparatur.');
      return;
    }
    if (!repairResp.ok) {
      const body = await repairResp.json().catch(() => ({}));
      showError(body.error || `Fehler ${repairResp.status} beim Anlegen.`);
      return;
    }
    const { repair_id, vehicle_url } = await repairResp.json();

    // 2. Upload each image sequentially.
    const baseUrl = `/vehicles/{{ registration_number }}/repairs/${repair_id}/images`;
    const entries = picker.pickerApi.getEntries();
    let failures = 0;
    for (const entry of entries) {
      picker.pickerApi.setStatus(entry.id, 'uploading');
      const ok = await uploadOne(entry, baseUrl);
      if (!ok) failures++;
    }

    // 3. Decide on redirect vs. banner.
    if (failures === 0) {
      banner.textContent = 'Alle Bilder hochgeladen. Weiterleitung…';
      banner.classList.remove('bg-yellow-100', 'text-yellow-900', 'border-yellow-300');
      banner.classList.add('bg-green-100', 'text-green-900', 'border-green-300');
      banner.hidden = false;
      setTimeout(() => { window.location.href = vehicle_url; }, 800);
    } else {
      const total = entries.length;
      banner.innerHTML =
        `Reparatur angelegt. ${total - failures} von ${total} Bildern hochgeladen. ` +
        `Du kannst fehlgeschlagene Bilder erneut versuchen oder ` +
        `<a class="underline" href="${vehicle_url}">zur Fahrzeug-Detailseite</a> weitergehen.`;
      banner.hidden = false;
      submit.hidden = true;
    }
  });

  async function uploadOne(entry, baseUrl) {
    const fd = new FormData();
    fd.set('image', entry.file, entry.file.name);
    let resp;
    try {
      resp = await fetch(baseUrl, {
        method: 'POST',
        headers: { 'Accept': 'application/json' },
        body: fd,
      });
    } catch (err) {
      picker.pickerApi.setStatus(entry.id, 'error', 'Netzwerk');
      picker.pickerApi.onRetry(entry.id, (e) => retryUpload(e, baseUrl));
      return false;
    }
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      picker.pickerApi.setStatus(entry.id, 'error', body.error || `HTTP ${resp.status}`);
      picker.pickerApi.onRetry(entry.id, (e) => retryUpload(e, baseUrl));
      return false;
    }
    picker.pickerApi.setStatus(entry.id, 'ok');
    return true;
  }

  async function retryUpload(entry, baseUrl) {
    picker.pickerApi.setStatus(entry.id, 'uploading');
    await uploadOne(entry, baseUrl);
  }

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
    submit.textContent = 'Anlegen';
    refreshSubmit();
  }

  refreshSubmit();
})();
</script>
{% endblock %}
```

- [ ] **Step 4.2: Run all repair-route tests — ensure nothing breaks**

Run: `uv run pytest tests/presentation/test_repairs.py -v`
Expected: alle Tests grün (insbesondere `test_new_repair_form_renders` — der prüft, dass das Template rendert).

- [ ] **Step 4.3: Manuell starten und sichten**

Run im Hintergrund:
```bash
uv run edelrep serve --storage-root ./storage --index-path ./index.db
```

Im Browser: <http://127.0.0.1:8080> → "+ Fahrzeug" → Stamm `99001` → Anlegen → "+ Reparatur" → die neue Form sollte sichtbar sein mit zwei Buttons "Foto aufnehmen" / "Bilder auswählen". Auswahl von 2 Test-JPEGs → Thumbnails erscheinen → Submit-Button wird aktiv → Klick → Redirect auf Vehicle-Detail-Seite mit beiden Bildern.

Server stoppen.

- [ ] **Step 4.4: Commit**

```bash
git add src/edelrep/presentation/templates/new_repair.html
git commit -m "$(cat <<'EOF'
feat(ui): Bilder direkt beim Anlegen einer Reparatur hochladen

new_repair.html bindet das image_picker-Macro ein und enthält die
Submit-Orchestrierung: Repair via JSON-Endpoint anlegen, dann Bilder
sequenziell hochladen mit Pro-Bild-Status. Mind. 1 Bild Pflicht
(Submit-Button disabled). Ohne JavaScript klassischer 303-Redirect
mit noscript-Hinweis auf Nachreich-Pfad.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `upload_image.html` — Macro einbinden + Multi-Upload-JS

**Files:**
- Modify: `src/edelrep/presentation/templates/upload_image.html`

- [ ] **Step 5.1: Replace the template content**

Ersetze den **gesamten** Inhalt von `src/edelrep/presentation/templates/upload_image.html` mit:

```jinja
{% extends "base.html" %}
{% from "_image_picker.html" import image_picker %}
{% block title %}Bilder hochladen{% endblock %}
{% block content %}
<h1 class="text-2xl font-bold mb-4">Bilder hochladen</h1>

<noscript>
  <form method="post"
        action="/vehicles/{{ registration_number }}/repairs/{{ repair_id }}/images"
        enctype="multipart/form-data" class="space-y-4">
    <input type="file" name="image" accept="image/*" required
           class="w-full p-3 border rounded bg-white">
    <button type="submit"
            class="bg-blue-600 text-white px-6 py-3 rounded font-semibold">
      Hochladen
    </button>
  </form>
</noscript>

<form id="upload-form" class="space-y-5"
      data-vehicle-url="/vehicles/{{ registration_number }}"
      data-images-url="/vehicles/{{ registration_number }}/repairs/{{ repair_id }}/images">
  {{ image_picker(name="repair_images") }}
  <div id="upload-banner" class="bg-yellow-100 border border-yellow-300 text-yellow-900 p-3 rounded text-sm" hidden></div>
  <button type="submit" id="upload-submit"
          class="bg-blue-600 hover:bg-blue-700 disabled:bg-slate-400 text-white px-6 py-3 rounded font-semibold"
          disabled>
    Hochladen
  </button>
</form>

<script>
(function () {
  const form = document.getElementById('upload-form');
  if (!form) return;
  const submit = document.getElementById('upload-submit');
  const banner = document.getElementById('upload-banner');
  const picker = form.querySelector('[data-image-picker]');
  const baseUrl = form.dataset.imagesUrl;
  const vehicleUrl = form.dataset.vehicleUrl;

  function refreshSubmit() {
    const count = picker.pickerApi ? picker.pickerApi.getEntries().length : 0;
    submit.disabled = count === 0;
  }
  picker.addEventListener('picker:change', refreshSubmit);
  refreshSubmit();

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    submit.disabled = true;
    submit.textContent = 'Lade hoch…';
    banner.hidden = true;

    const entries = picker.pickerApi.getEntries();
    let failures = 0;
    for (const entry of entries) {
      picker.pickerApi.setStatus(entry.id, 'uploading');
      const ok = await uploadOne(entry);
      if (!ok) failures++;
    }

    if (failures === 0) {
      banner.textContent = 'Alle Bilder hochgeladen. Weiterleitung…';
      banner.classList.remove('bg-yellow-100', 'text-yellow-900', 'border-yellow-300');
      banner.classList.add('bg-green-100', 'text-green-900', 'border-green-300');
      banner.hidden = false;
      setTimeout(() => { window.location.href = vehicleUrl; }, 800);
    } else {
      const total = entries.length;
      banner.innerHTML =
        `${total - failures} von ${total} Bildern hochgeladen. ` +
        `Du kannst fehlgeschlagene erneut versuchen oder ` +
        `<a class="underline" href="${vehicleUrl}">zur Fahrzeug-Detailseite</a> weitergehen.`;
      banner.hidden = false;
      submit.hidden = true;
    }
  });

  async function uploadOne(entry) {
    const fd = new FormData();
    fd.set('image', entry.file, entry.file.name);
    let resp;
    try {
      resp = await fetch(baseUrl, {
        method: 'POST',
        headers: { 'Accept': 'application/json' },
        body: fd,
      });
    } catch (err) {
      picker.pickerApi.setStatus(entry.id, 'error', 'Netzwerk');
      picker.pickerApi.onRetry(entry.id, retryUpload);
      return false;
    }
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      picker.pickerApi.setStatus(entry.id, 'error', body.error || `HTTP ${resp.status}`);
      picker.pickerApi.onRetry(entry.id, retryUpload);
      return false;
    }
    picker.pickerApi.setStatus(entry.id, 'ok');
    return true;
  }

  async function retryUpload(entry) {
    picker.pickerApi.setStatus(entry.id, 'uploading');
    await uploadOne(entry);
  }
})();
</script>
{% endblock %}
```

- [ ] **Step 5.2: Run all image-route tests**

Run: `uv run pytest tests/presentation/test_images.py -v`
Expected: alle Tests grün (insbesondere `test_upload_form_renders` und `test_upload_image_redirects_to_vehicle_detail` — letzterer prüft den No-JS-303-Pfad, der über den `<noscript>`-Form weiterhin verfügbar ist — der Test selbst submittet jedoch ohne JS-Beteiligung gegen den Endpoint, das funktioniert weiterhin direkt).

- [ ] **Step 5.3: Manuell sichten**

Server starten (siehe Task 4.3). Bestehende Reparatur öffnen → "Bilder hochladen →" → die neue Multi-Upload-Komponente sollte sichtbar sein, mehrere Bilder testen, Submit, Redirect.

Server stoppen.

- [ ] **Step 5.4: Commit**

```bash
git add src/edelrep/presentation/templates/upload_image.html
git commit -m "$(cat <<'EOF'
feat(ui): Multi-Image-Upload für nachträglichen Bild-Upload

upload_image.html bindet dasselbe image_picker-Macro ein wie
new_repair.html und ermöglicht so Multi-Upload mit Pro-Bild-Status
auch beim Nachreichen. noscript-Variante hält den Single-File-Upload
für JS-freie Browser am Leben.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Manueller Test-Pfad + Gesamtverifikation

**Files:**
- Read-only verification

- [ ] **Step 6.1: Volle Test-Suite laufen lassen**

Run: `uv run pytest`
Expected: alle 499+ Tests grün (sechs neue dazu = 505+).

- [ ] **Step 6.2: Type-Check**

Run: `uv run pyright`
Expected: keine neuen Fehler.

- [ ] **Step 6.3: Lint + Format**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: kein Output ausser "All checks passed" / "X files already formatted".

Wenn `format --check` Diffs zeigt: `uv run ruff format` ausführen, ändern, in Task 7 mit-committen.

- [ ] **Step 6.4: Manuelle Browser-Tests (Desktop + Mobile)**

Server starten:
```bash
uv run edelrep serve --storage-root ./storage --index-path ./index.db --host 0.0.0.0
```

**Desktop (Chrome/Firefox):**
- [ ] Fahrzeug `90001` anlegen → "+ Reparatur" → Beschreibung + Datum eingeben → Submit-Button bleibt **disabled** (kein Bild gewählt).
- [ ] "📁 Bilder auswählen" → 3 JPEGs aus Filesystem wählen → 3 Thumbnails erscheinen → Submit aktiv.
- [ ] Submit → Status pro Bild wechselt von 🕐 → 🔄 → ✅ → Auto-Redirect.
- [ ] "📷 Foto aufnehmen" → öffnet Datei-Picker (Desktop hat keine Kamera-Capture) — kein Crash.
- [ ] Bild >25 MB hinzufügen → roter Eintrag "Zu gross", **nicht** zählbar als gültig (Submit bleibt disabled bei nur diesem einen Bild).
- [ ] Same-name Duplikat hinzufügen → Hinweistext "ist bereits ausgewählt".
- [ ] ✕-Button entfernt Eintrag → Submit-Status aktualisiert sich.
- [ ] JS deaktivieren (DevTools) → Submit funktioniert klassisch ohne Bild → Redirect.

**Mobile (LAN-IP, iOS Safari + Android Chrome):**
- [ ] LAN-IP des Servers im Telefon-Browser öffnen.
- [ ] "+ Reparatur" für ein Test-Fahrzeug → "📷 Foto aufnehmen" → Kamera öffnet sich direkt → Foto machen → Thumbnail erscheint → "📁 Bilder auswählen" → Galerie/Photos-Picker mit Mehrfach-Auswahl → 2 weitere wählen → 3 Thumbnails total → Submit → alle hochgeladen → Redirect.

Server stoppen.

- [ ] **Step 6.5: Commit (falls Format-Änderungen)**

Falls Step 6.3 zu `ruff format`-Änderungen geführt hat:
```bash
git add -u
git commit -m "$(cat <<'EOF'
chore: ruff format nach repair-with-image-upload

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Sonst: kein Commit nötig.

---

## Done-Definition

- Alle Tests grün, Pyright und Ruff ohne neue Befunde.
- Reparatur kann mit ein oder mehreren Bildern in einem Schritt angelegt werden (Desktop, iOS, Android manuell verifiziert).
- Pro-Bild-Status wird live angezeigt; fehlgeschlagene Bilder können einzeln erneut versucht werden.
- Nachträglicher Upload (`/upload`-Seite) bietet dieselbe Multi-Upload-Erfahrung.
- Ohne JS funktionieren beide Seiten weiterhin (klassischer Single-File-Form, Redirect).
- Bestehende 303-Redirect-Tests sind grün (Regression-Schutz).
