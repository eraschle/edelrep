# Bild-Kommentare, Repair-Sortierung mit Tiebreaker, Fahrzeug-Dropdown mit Fuzzy Search

**Status:** Design — bereit für Plan
**Datum:** 2026-05-10
**Scope:** Drei Features in einem Spec, weil sie sich gemeinsam in einem Implementierungs-Plan abarbeiten lassen.

---

## Ziel

Drei UX-Verbesserungen für die Werkstatt-Praxis:

1. **Bild-Kommentare** — pro Bild ein optionaler Freitext, beim Upload erfassbar oder nachträglich über ein Modal bearbeitbar.
2. **Stabile Reparatur-Sortierung** — Reparaturen am selben Tag sortieren deterministisch nach `created_at` (heute unspezifiziert).
3. **Fahrzeug-Übersicht mit Fuzzy Search** — die Suchseite zeigt initial alle Fahrzeuge, absteigend nach letzter Aktivität; Eingabe filtert per Fuzzy Match.

## Nutzungs-Szenarien

- **Mechaniker beim Foto-Upload:** Pro Bild beschreibt eine kurze Notiz, was zu sehen ist ("Bremsbelag rechts, neuer Typ").
- **Werkstatt-Leiter bei Rückfragen:** Findet auf der Fahrzeug-Detailseite ein älteres Bild und ergänzt nachträglich einen Kontext-Hinweis übers Modal.
- **Mechaniker am Suchfeld:** Tippt eine Stammnummer mit Vertipper ("1234" statt "1243") und bekommt trotzdem das richtige Fahrzeug. Oder klickt auf `/search`, scrollt durch die zuletzt bearbeiteten Fahrzeuge ohne zu tippen.

---

## Entscheidungen aus Brainstorming

| Frage | Entscheidung |
|-------|--------------|
| Storage für Kommentare | Neuer Sidecar pro Bild: `<reg>/<repair-dir>/NNNN_<ulid>.json` |
| Schema-Version | `1`, identisches Atomic-Write-Pattern wie bestehende Sidecars |
| Max Länge Kommentar | 1000 Zeichen (Whitespace-only → `None`) |
| Edit-UX | Modal/Popup nach Klick aufs Thumbnail oder Stift-Icon |
| Anzeige auf Detail-Seite | Erste Zeile gekürzt unter dem Thumbnail (Truncate / `line-clamp-2`) |
| Index | Kommentar **nicht** in SQLite-Index, **nicht** durchsuchbar |
| Reparatur-Tiebreaker | `created_at` DESC nach `date` DESC |
| "Letzte Aktivität" pro Fahrzeug | `max(jüngste Repair-Zeit, jüngste Image-Zeit, vehicle.created_at)`, alle aus ULID-Timestamps bzw. Vehicle-Sidecar ableitbar |
| Dropdown-UX | Bestehende Suchseite umbauen, initial alle Fahrzeuge zeigen |
| Fuzzy-Engine | Server-seitig mit `rapidfuzz` (neue Dependency) |
| Pagination | Statisches Limit 200 für Initial-Liste; 50 für Fuzzy-Ergebnisse |

---

## Architektur

### Schicht-Übersicht

```
Presentation
├─ routes/images.py     (POST erweitert um `comment`, neuer PATCH /images/{id}/comment)
├─ routes/search.py     (GET /search rendert volle Liste; /search/suggestions unverändert in Signatur)
├─ templates/_image_picker.html   (Textarea pro Eintrag)
├─ templates/vehicle_detail.html  (Caption + Modal)
└─ templates/search.html          (Initial-State zeigt volle Liste)

Application
├─ upload_image.py     (UploadImageUseCase nimmt `comment: str | None`)
├─ update_image_comment.py  [NEU]
└─ search_vehicle.py   (SearchVehicleUseCase erhält FuzzyMatcher, leerer Query → Activity-Liste)

Domain
├─ entities.py         (Image.comment: str | None hinzu, Konstruktor validiert)
├─ ports/image_repository.py  (neue Methode update_comment)
├─ ports/search_index.py      (neue Methode list_vehicles_by_activity)
└─ ports/fuzzy_matcher.py     [NEU] Protocol mit score()

Infrastructure
├─ filesystem/image_store.py  (Sidecar lesen/schreiben, neue Methode update_comment)
├─ filesystem/layout.py       (Helpers image_sidecar_key, is_image_sidecar_key)
├─ filesystem/sidecar.py      (unverändert — reuse)
├─ index/sqlite_search_index.py  (neue Methode list_vehicles_by_activity)
├─ search/rapidfuzz_matcher.py   [NEU]
└─ watcher/                   (Image-Sidecar-Keys filtern, sonst Drift)
```

Abhängigkeitsrichtung unverändert (Presentation → Application → Domain ← Infrastructure). Keine neuen Cross-Layer-Kopplungen.

---

## Feature 1 — Bild-Kommentare

### Domain

`src/edelrep/domain/entities.py`:

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
    comment: str | None = None   # NEU

    def __post_init__(self) -> None:
        _require_aware(self.uploaded_at, "uploaded_at")
        if self.captured_at is not None:
            _require_aware(self.captured_at, "captured_at")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        if self.comment is not None and len(self.comment) > 1000:
            raise ValueError("comment too long (max 1000 chars)")
```

Whitespace-only-Strings werden bereits in Application-/Presentation-Layer auf `None` normalisiert; die Domain prüft nur die Länge.

### Persistierung — Image-Sidecar

Neue Datei je Bild: `<reg>/<repair-dir>/NNNN_<ulid>.json` (Geschwister des JPEGs, identische `seq`/`ulid`):

```json
{
  "schema_version": 1,
  "comment": "Bremsbelag rechts, neuer Typ"
}
```

`src/edelrep/infrastructure/filesystem/layout.py`:

```python
_IMAGE_SIDECAR_KEY_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}/\d{4}-\d{2}-\d{2}__[a-z0-9-]+"
    r"/\d{4}_[0-9A-HJKMNP-TV-Z]{26}\.json$"
)

def image_sidecar_key(vehicle_id: VehicleId, dir_name: str, image_filename_value: str) -> str:
    # image_filename_value = "NNNN_<ulid>.<ext>" → ersetzt durch ".json"
    stem = image_filename_value.rsplit(".", 1)[0]
    return f"{vehicle_id.registration_number}/{dir_name}/{stem}.json"

def is_image_sidecar_key(key: str) -> bool:
    return bool(_IMAGE_SIDECAR_KEY_RE.match(key))
```

`src/edelrep/infrastructure/filesystem/image_store.py`:

- `save(image, raw_bytes=…, thumbnail_bytes=…)`: nach dem Schreiben des JPEGs/Thumbnails — falls `image.comment` nicht `None` — `write_backend_sidecar(...)` mit `{"comment": image.comment}` aufrufen.
- `_reconstruct(key, repair_id)`: nach dem Bauen des Image-Objekts den Sidecar-Key bilden; wenn er existiert, JSON lesen und `comment=data["comment"]` setzen. Sonst `comment=None`.
- Neue Methode `update_comment(image_id: ULID, comment: str | None) -> None`:
  - Bild-Key suchen (gleiches Pattern wie `get`).
  - Wenn `comment is None`: Sidecar löschen, falls vorhanden. Sonst `write_backend_sidecar` mit neuem Wert.
  - Raises `ImageNotFound`, wenn das Bild nicht existiert.

`ImageRepository`-Port (`src/edelrep/domain/ports/image_repository.py`):

```python
def update_comment(self, image_id: ULID, comment: str | None) -> None:
    """Set or clear the comment for an image. Raises ImageNotFound."""
    ...
```

### Watcher

`src/edelrep/infrastructure/watcher/` muss `*.json`-Dateien neben Image-Files erkennen und ihnen den passenden Image-Datensatz zuordnen, sonst löst jeder Kommentar-Edit eine Drift-Warnung aus.

- `KeyEventHandler` filtert `_thumbs/` heute schon. Image-Sidecars werden **nicht** gefiltert: sie sollen einen `upsert_image` triggern, damit künftige Index-Felder konsistent bleiben (auch wenn aktuell `comment` nicht im Index landet).
- Im Mapping von Storage-Key → Domain-Entity (Debouncer-Flush) muss `is_image_sidecar_key(key)` zum entsprechenden Image-Read übersetzen (gleiche Repair-ID wie das JPEG-Geschwister).

### Application

`src/edelrep/application/upload_image.py`:

- `execute(...)` bekommt neuen Keyword-Parameter `comment: str | None = None`.
- Whitespace-Stripping: `comment = comment.strip() if comment else None; comment = comment or None`.
- `Image(...)` mit `comment=comment` konstruieren.

Neuer Use-Case `src/edelrep/application/update_image_comment.py`:

```python
class UpdateImageCommentUseCase:
    def __init__(self, image_repo: ImageRepository) -> None:
        self._image_repo = image_repo

    def execute(self, image_id: ULID, comment: str | None) -> Image:
        normalised = comment.strip() if comment else None
        normalised = normalised or None
        if normalised is not None and len(normalised) > 1000:
            raise ValueError("comment too long (max 1000 chars)")
        self._image_repo.update_comment(image_id, normalised)
        return self._image_repo.get(image_id)
```

### Container

`src/edelrep/presentation/container.py`: `update_image_comment: UpdateImageCommentUseCase` neu im `Container`, in `build_container` verdrahten.

### Routen

`src/edelrep/presentation/routes/images.py`:

- `POST /vehicles/{registration_number}/repairs/{repair_id}/images` bekommt `comment: str = Form("")` (FastAPI-Form-Field). Wird an Use-Case durchgereicht (leerer String → `None` via Strip).
- Neu: `PATCH /images/{image_id}/comment` (JSON-Body `{"comment": "..."}` oder `{"comment": null}`).
  - Validierung: 422 bei zu langem Kommentar oder kaputtem JSON.
  - Erfolg: 200 mit `{"image_id": "...", "comment": "<normalisierter Wert oder null>"}`.
  - Fehler `ImageNotFound`: 404.

### UI — Upload

`src/edelrep/presentation/templates/_image_picker.html`:

- Pro Eintrag wird im `<template data-picker-entry-template>` ein zusätzliches Textarea-Feld hinzugefügt (oder ein zweiter `<div>` unter Meta/Status):
  ```html
  <textarea data-entry-comment maxlength="1000"
            placeholder="Kommentar (optional)"
            class="mt-2 w-full text-sm border border-slate-200 rounded-md px-2 py-1 resize-y" rows="1"></textarea>
  ```
- `pickerApi.getEntries()` liefert pro Eintrag zusätzlich `comment: el.querySelector('[data-entry-comment]').value`.

`templates/new_repair.html` und `templates/upload_image.html`:

- `uploadOne(entry, baseUrl)`: `FormData` bekommt `fd.set('comment', entry.commentEl.value)` vor dem POST.
- `pickerApi.setStatus(...)` und Retry-Pfad bleiben unverändert.

### UI — Anzeige & Modal

`src/edelrep/presentation/templates/vehicle_detail.html`:

- Unter jedem Thumbnail die erste Zeile des Kommentars rendern, gekürzt:
  ```html
  {% if img.comment %}
  <p class="mt-1 text-xs text-slate-600 line-clamp-2 max-w-[6rem]">{{ img.comment }}</p>
  {% endif %}
  ```
- Klick aufs Thumbnail öffnet das Modal (statt direkten `target="_blank"`-Link auf `/images/{id}/raw`).
- Neues Modal (am Seitenende, `hidden` per Default):
  ```html
  <div id="image-modal" class="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" hidden>
    <div class="bg-white rounded-xl max-w-3xl w-full max-h-[90vh] overflow-auto p-4 space-y-3">
      <div class="flex justify-between items-center">
        <span data-modal-filename class="font-medium text-sm truncate"></span>
        <button type="button" data-modal-close aria-label="Schliessen"
                class="text-slate-400 hover:text-slate-900">×</button>
      </div>
      <img data-modal-image alt="" class="w-full h-auto rounded-lg">
      <a data-modal-raw target="_blank" class="text-sm text-blue-600 hover:underline">In neuem Tab öffnen</a>
      <form data-modal-form class="space-y-2">
        <label class="block text-sm font-medium">Kommentar</label>
        <textarea data-modal-comment maxlength="1000" rows="3"
                  class="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"></textarea>
        <div class="flex justify-end gap-2">
          <span data-modal-status class="text-xs text-slate-500"></span>
          <button type="submit"
                  class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium">
            Speichern
          </button>
        </div>
      </form>
    </div>
  </div>
  ```
- Inline-Skript am Seitenende: öffnet das Modal mit `data-image-id`, `data-image-comment`, `data-image-filename` aus dem geklickten Thumbnail-Element. Speichern → `PATCH /images/{id}/comment`. Bei Erfolg DOM-Caption auf der Liste aktualisieren und Modal schliessen.

### Migration / Backward-Compat

- Bestehende Bilder ohne Sidecar werden mit `comment=None` rekonstruiert.
- Kein expliziter Migrations-Schritt nötig. `edelrep reindex` bleibt funktional unverändert (Index speichert keinen Kommentar).

### Architektur-Doku

`docs/architecture.md` Z. 125 ("Pro Bild gibt es **keine** Sidecar-Datei in V1") wird ersetzt durch eine Erklärung des optionalen Image-Sidecars (Schema, Lese-Default, kein Index-Cache).

---

## Feature 2 — Reparatur-Sortierung mit Tiebreaker

### Änderung

`src/edelrep/infrastructure/filesystem/repair_store.py:78`:

```python
repairs.sort(key=lambda r: (r.date, r.created_at), reverse=True)
```

(statt `key=lambda r: r.date`)

### Konsequenzen

- Domain/Application/Ports/Index/UI: unverändert.
- `ListRepairsUseCase` und `vehicle_detail.html` profitieren automatisch.

### Tests

- `tests/infrastructure/filesystem/test_repair_store.py` (oder gleichwertig): "two repairs same date, different created_at → ordered by created_at DESC".
- Optionale Spiegelung in `tests/application/test_list_repairs.py` mit Fake-Repo, falls dort ein passendes Pattern existiert.

---

## Feature 3 — Fahrzeug-Übersicht mit Fuzzy Search

### Domain — neuer Port `FuzzyMatcher`

`src/edelrep/domain/ports/fuzzy_matcher.py`:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class FuzzyMatcher(Protocol):
    """Returns a 0..100 similarity score for query vs. candidate text."""
    def score(self, query: str, candidate: str) -> float: ...
```

Re-export in `domain/ports/__init__.py`.

### Domain — `SearchIndex` erweitert

`src/edelrep/domain/ports/search_index.py`:

```python
def list_vehicles_by_activity(self, limit: int) -> Iterable[Vehicle]:
    """Iterate vehicles, most-recently-active first.

    Activity is the maximum of (most recent repair, most recent image
    upload, vehicle.created_at). Implementations decide how they
    materialise this ranking.
    """
    ...
```

### Infrastructure — `RapidFuzzMatcher`

Neue Dependency `rapidfuzz` in `pyproject.toml`.

`src/edelrep/infrastructure/search/rapidfuzz_matcher.py`:

```python
from rapidfuzz import fuzz

class RapidFuzzMatcher:
    def score(self, query: str, candidate: str) -> float:
        if not query or not candidate:
            return 0.0
        return float(fuzz.WRatio(query, candidate))
```

### Infrastructure — `SqliteSearchIndex.list_vehicles_by_activity`

```python
def list_vehicles_by_activity(self, limit: int) -> Iterable[Vehicle]:
    if limit < 1:
        return []
    with self._lock:
        rows = self._conn.execute(
            """
            SELECT v.registration_number, v.vin, v.description, v.created_at,
                   (SELECT MAX(id) FROM repairs WHERE registration_number = v.registration_number) AS last_repair_id,
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

Der zentrale Kniff: ULIDs liefern via `python-ulid` ein `.datetime`-Property — kein zusätzliches Zeitfeld in den Tabellen nötig.

### Application — `SearchVehicleUseCase` erweitert

`src/edelrep/application/search_vehicle.py`:

```python
class SearchVehicleUseCase:
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
                # idx als Activity-Tiebreaker — candidates ist bereits DESC sortiert
                scored.append((best, -idx, v))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return [v for _, _, v in scored[:limit]]
```

### Container

`build_container(...)`: `RapidFuzzMatcher()` instanzieren und `SearchVehicleUseCase(search_index, fuzzy=matcher)` verdrahten.

### Web-UI — Suchseite

`src/edelrep/presentation/routes/search.py`:

```python
@router.get("/search", response_class=HTMLResponse)
def search_page(request: Request, container: ContainerDep) -> HTMLResponse:
    results = container.search_vehicle.execute("", limit=200)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "search.html", {"results": results})
```

`/search/suggestions` bleibt strukturell gleich, ruft denselben Use-Case auf (leerer Query → Full-List).

`templates/search.html`:

```jinja
{% block content %}
<h1 class="text-3xl font-bold mb-6 tracking-tight">Fahrzeug suchen</h1>
<div class="relative mb-6">
  ...
  <input type="search" name="q"
         placeholder="Stammnummer, Rahmennummer oder Beschreibung – Tippfehler erlaubt"
         hx-get="/search/suggestions"
         hx-trigger="keyup changed delay:200ms, search"
         hx-target="#suggestions"
         ...>
</div>
<div id="suggestions">
  {% include "_vehicle_search_results.html" %}
</div>
{% endblock %}
```

`templates/_vehicle_search_results.html`:

- Leere `results`-Liste: differenziert zwischen "keine Fahrzeuge angelegt" und "keine Treffer". Das Server-Template entscheidet anhand eines Context-Flags `is_empty_filter = q != ""` (vom Route mitgegeben).

---

## Validierung & Edge Cases

### Bild-Kommentare

- **Whitespace-only Input** → `None` (kein leerer Sidecar, kein 0-Byte-Eintrag).
- **Kommentar löschen** = leeren String submitten → Sidecar wird entfernt.
- **Kommentar > 1000 Zeichen** → 422 vom PATCH-Endpoint, Client-Validierung über `maxlength`.
- **Reload mitten im Modal-Speichern**: Modal hat keinen optimistischen Refresh — Erfolg wird auf Server-Antwort gewartet. Bei Netzwerk-Fehler bleibt Modal offen mit Fehler-Hinweis.
- **Watcher und Sidecar**: Image-Sidecar-Writes triggern den `KeyEventHandler`. Das Mapping muss den Sidecar-Key auf das zugehörige Bild auflösen, sonst gibt es bei jedem Kommentar-Edit unnötige Drift-Marker.
- **Concurrency**: Single-Process LAN-V1 (per Architektur-Doku) — kein zusätzlicher Schutz nötig.

### Repair-Sortierung

- Falls `created_at` gleich (millisecond collisions): Reihenfolge bleibt deterministisch durch Listen-Iteration, aber theoretisch nicht garantiert. Ist akzeptabel (extrem unwahrscheinlich; Workflow hat menschliche Latenz dazwischen).

### Fahrzeug-Dropdown

- **Leere DB**: `/search` zeigt "Noch keine Fahrzeuge angelegt.".
- **Query ohne Treffer**: "Keine Treffer für "<query>".".
- **Sehr kurze Queries (1–2 Zeichen)**: `WRatio` liefert für sehr kurze Queries oft hohe Scores für viele Kandidaten. Threshold 60 lässt einiges durch; das ist akzeptabel (eher mehr als weniger zeigen).
- **Performance**: Bei 1000 Fahrzeugen pro Suggestion-Request: `list_vehicles_by_activity(1000)` ist ein einzelner SQL-Query plus ULID-Parsing in Python (~Millisekunden). Fuzzy-Scoring über drei Felder × 1000 Kandidaten = 3000 `WRatio`-Aufrufe (~10ms). Akzeptabel.
- **Fahrzeuge ohne Reparaturen/Bilder**: Fallback auf `vehicle.created_at` — erscheinen je nach Anlagedatum oben oder unten.

---

## Test-Strategie

### Domain
- `tests/domain/test_entities.py`: `Image(comment=...)` mit gültigem Wert, mit `None`, mit zu langem String (raises `ValueError`).
- `tests/domain/ports/test_fuzzy_matcher.py`: Protocol-Smoke-Test mit Dummy-Implementierung.

### Application
- `tests/application/test_upload_image.py`: Upload mit `comment="Foo"` und mit `comment=None`; Bytes identisch, nur Sidecar-Write unterscheidet sich.
- `tests/application/test_update_image_comment.py` (neu): `execute` setzt/löscht Kommentar; `execute` mit zu langem String wirft.
- `tests/application/test_search_vehicle.py`:
  - leerer Query → ruft `list_vehicles_by_activity`.
  - Fuzzy-Query mit Vertipper findet das richtige Fahrzeug.
  - Threshold filtert Random-Strings raus.
  - `limit=0` raises.

### Infrastructure
- `tests/infrastructure/filesystem/test_image_store.py`: Save mit Kommentar erzeugt Sidecar; `_reconstruct` liest Kommentar; `update_comment(None)` löscht Sidecar; `update_comment` auf nicht-existierendes Bild raises `ImageNotFound`.
- `tests/infrastructure/filesystem/test_repair_store.py`: zwei Reparaturen gleichen Datums, unterschiedliches `created_at` → DESC-Reihenfolge nach `created_at`.
- `tests/infrastructure/search/test_rapidfuzz_matcher.py`: identisch=100, kompletter Mismatch ≈ 0, Vertipper hoher Score.
- `tests/infrastructure/index/test_sqlite_search_index.py`: `list_vehicles_by_activity` mit drei Fahrzeugen (Fahrzeug A mit später Reparatur, Fahrzeug B mit nur einem Bild, Fahrzeug C ohne alles) → Reihenfolge A > B > C.
- `tests/infrastructure/watcher/`: Image-Sidecar-Write triggert `upsert_image` (Drift-frei).

### Presentation
- `tests/presentation/test_images.py`:
  - POST mit Form-Field `comment="text"` → Bild-Sidecar persistiert; Reconstruction liefert `comment="text"`.
  - PATCH `/images/{id}/comment` mit `{"comment":"new"}` → 200, Persistierung, Reconstruction.
  - PATCH mit `{"comment":null}` → Sidecar gelöscht.
  - PATCH zu langer String → 422.
  - PATCH unbekannte Image-ID → 404.
- `tests/presentation/test_search.py`:
  - `GET /search` rendert volle Liste in Activity-Reihenfolge.
  - `GET /search/suggestions?q=` (leer) → Full-List.
  - `GET /search/suggestions?q=12X4` (Vertipper) → findet Fahrzeug `1234`.
- `tests/presentation/test_e2e_click_path.py` ergänzt um:
  - Foto mit Kommentar hochladen → Detail-Seite zeigt Caption.
  - Thumbnail-Klick öffnet Modal, Kommentar ändern, Modal-Schliessen, Caption aktualisiert.

### Quality Gates (unverändert)

- `uv run pyright` 0 Errors.
- `uv run pytest --cov=edelrep` grün, Coverage ≥ 95% gesamt, ≥ 90% pro neue Datei.
- `uv run ruff check . && ruff format --check .` clean.
- Domain-Import-Guard: keine neuen Verbote.
- Application-Import-Guard: keine neuen Verbote.

---

## Out-of-Scope

- HEIC/HEIF-Verarbeitung.
- Drag & Drop, Bild-Reihenfolge umsortieren.
- Bild-Kommentar in FTS-Index aufnehmen.
- Manuelle "Festpinnen"-Funktion auf der Suchseite.
- Pagination/Infinite-Scroll auf `/search`.
- Navbar-Dropdown für Fahrzeuge.
- Mehrsprachigkeit (deutsche Labels bleiben).
- `updated_at`-Feld im Vehicle-Sidecar (Activity wird abgeleitet, nicht persistiert).
- Auth/Login (LAN-only bleibt).
- E-Mail-Ingestion: kein Pfad zu Kommentaren via Mail in V1 (Mail liefert nur Bilder).

---

## Risiken & Annahmen

- **rapidfuzz-Lizenz und Wheel-Verfügbarkeit für Python 3.13** — MIT-Lizenz, Wheels publiziert; sollte konfliktfrei sein. `uv sync` validiert.
- **ULID-Timestamp-Konvertierung**: `python-ulid` liefert `.datetime` direkt; getestet im bestehenden Projekt.
- **Watcher-Drift bei Sidecar-Writes**: höchstes Risiko. Plan-Phase muss `is_image_sidecar_key` im `KeyEventHandler`-Pfad nachweislich verdrahten und mit einem Watcher-Test absichern.
- **Annahme: Bestandsdaten sind klein** (< wenige tausend Fahrzeuge). Bei 100k+ braucht `list_vehicles_by_activity` zwingend einen materialisierten Aktivitäts-Wert; das ist im Out-of-Scope.
