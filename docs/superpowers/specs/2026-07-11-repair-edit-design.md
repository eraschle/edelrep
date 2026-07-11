# Reparatur bearbeiten (Beschreibung + Foto-Upload)

**Status:** Design — bereit für Plan
**Datum:** 2026-07-11
**Scope:** Bestehende Reparaturen bearbeitbar machen: Beschreibung anpassen und neue Fotos hochladen. Enthält einen Bugfix im Live-Index, den dieses Feature auslöst.

---

## Ziel

Der Mechaniker soll eine bereits angelegte Reparatur nachträglich bearbeiten können:

1. **Beschreibung anpassen** — Freitext der Reparatur ändern (heute nur beim Anlegen setzbar).
2. **Neue Fotos hochladen** — nutzt den bestehenden Upload-Flow.

Das **Datum bleibt unveränderlich** (es ist Teil der Ordner-Identität auf der Platte).

## Nutzungs-Szenarien

- **Mechaniker korrigiert einen Tippfehler:** Öffnet eine Reparatur, ändert die Beschreibung von "Bremsen vorn" auf "Bremsen vorne + Bremsflüssigkeit" und speichert.
- **Mechaniker ergänzt Fotos:** Lädt zu einer bestehenden Reparatur weitere Bilder nach (bereits existierender Upload-Flow, jetzt konsistent verlinkt von der Bearbeiten-Seite).

---

## Entscheidungen aus Brainstorming

| Frage | Entscheidung |
|-------|--------------|
| Editierbare Felder | **Nur Beschreibung** (+ Foto-Upload). Datum unveränderlich. |
| Ordner-Slug bei Beschreibungsänderung | **Ordner stabil lassen** — kein Umbenennen/Verschieben von Dateien. Sidecar wird in-place aktualisiert. |
| UX-Muster | **Eigene Edit-Seite** (analog `edit_vehicle.html`), erreichbar über "Bearbeiten"-Link pro Reparatur-Karte. |
| Index-Zugriff im Use-Case | **Keiner** — wie `CreateRepairUseCase`. Index-Konsistenz übernimmt der Live-Watcher (`_handle_repair`) bzw. der volle Reindex. |
| Foto-Upload | Bestehender Flow (`upload_image.html`), von der Edit-Seite verlinkt. |

---

## Wichtige Architektur-Erkenntnisse (verifiziert)

Diese Fakten begründen das Design und wurden im Code geprüft:

1. **Der Reparatur-Ordnername kodiert Datum + Beschreibung** (`<vehicle_ulid>/<YYYY-MM-DD>__<slug>/`), und alle Fotos liegen in diesem Ordner. Bilder werden aber über die Reparatur-ULID in der `_repair.json`-Sidecar aufgelöst — eine Beschreibungsänderung **bricht die Bildzuordnung nicht**.
2. **`RepairRepository.update()` existiert bereits** und schreibt die Sidecar in-place (benennt den Ordner **nicht** um). Es hat aktuell **keinen** Consumer — dieses Feature ist der erste, definiert also die Semantik.
3. **Die Reparatur-Beschreibung ist nicht durchsuchbar.** Die FTS-Suche deckt nur `vehicles` ab (registration_number, vin, description). Die `repairs.description`-Spalte im Index wird nirgends per Inhalt abgefragt (nur `MAX(id)` fürs Recency-Ranking). Bearbeiten der Reparatur-Beschreibung beeinflusst die Suche also nicht.
4. **`repairs.folder_name` im Index wird nur geschrieben, nie gelesen** (keine Query selektiert es).
5. **`DriftDetector` vergleicht nur mtimes**, berechnet keine Slugs neu — die Ordner/Beschreibung-Divergenz löst keine Reindex-Schleife aus.
6. **`CreateRepairUseCase` fasst den Index nicht an** — neue Reparaturen werden ausschliesslich vom Live-Watcher indexiert. Etabliertes Muster: *Use-Case schreibt Dateisystem, Watcher projiziert in den Index.*

---

## Architektur

### Schicht-Übersicht

```
Application
└─ update_repair.py          (NEU: UpdateRepairUseCase)

Infrastructure
└─ watcher/live_index.py     (Bugfix: _handle_image ordnet Bilder robust zu)

Presentation
├─ routes/repairs.py         (NEU: GET+POST /vehicles/{key}/repairs/{id}/edit)
├─ templates/edit_repair.html(NEU)
├─ templates/vehicle_detail.html ("Bearbeiten"-Link pro Reparatur-Karte)
└─ container.py              (update_repair verdrahten)
```

### 1. `UpdateRepairUseCase` (`application/update_repair.py`)

Analog zu `CreateRepairUseCase`, **ohne** Index-Zugriff.

- Signatur: `execute(*, repair_id: ULID, description: str | None) -> Repair`
- Ablauf:
  1. `existing = self._repair_repo.get(repair_id)` — wirft `RepairNotFound`, wenn nicht vorhanden.
  2. Neue `Repair` bauen: `id`, `vehicle_id`, `date`, `created_at` unverändert von `existing`; `description` = normalisiert (`description.strip()` falls gesetzt, leer → `None`).
  3. `self._repair_repo.update(updated)` — schreibt Sidecar in-place, Ordner bleibt stabil.
  4. `return updated`.
- Dependencies: nur `repair_repo: RepairRepository`.

### 2. Bugfix `live_index._handle_image`

**Problem (durch dieses Feature ausgelöst):** Der Watcher ordnet ein neu hochgeladenes Bild seiner Reparatur zu, indem er `repair_dir_name(repair.date, repair.description)` neu berechnet und mit dem Ordnernamen auf der Platte vergleicht (`live_index.py:129-130`). Nach einer Beschreibungsänderung (Ordner bleibt beim alten Slug) divergieren beide → das neue Foto wird **nicht** indexiert → das Recency-Ranking der Fahrzeugliste (`list_vehicles_by_activity`, `MAX(i.id)`) reflektiert den Upload nicht.

**Fix:** Reparatur robust über die `_repair.json`-Sidecar **im selben Ordner** auflösen statt über Slug-Neuberechnung:
- Aus dem Image-Key `vehicle_str/dir_name` ableiten, die Sidecar `<root>/<vehicle_str>/<dir_name>/_repair.json` lesen und die Reparatur-ULID entnehmen.
- Die passende Reparatur aus `list_for_vehicle(vehicle.id)` per **ID** finden (statt per Slug), dann wie bisher deren Bilder projizieren.
- Wenn keine Sidecar/Reparatur gefunden wird: no-op (wie bisher bei Nichttreffer).

Dies ist strikt korrekter als die Slug-Neuberechnung und entfernt die Fragilität dauerhaft.

### 3. Presentation

**Route GET** `/vehicles/{vehicle_key}/repairs/{repair_id}/edit`:
- Fahrzeug via `resolve_vehicle` auflösen (404 `VehicleNotFound`).
- `repair_id` als ULID parsen (404 bei Formatfehler); `container.repair_repo.get(rid)` (404 `RepairNotFound`).
- Prüfen, dass `repair.vehicle_id == vehicle.id` (sonst 404).
- Rendert `edit_repair.html` mit `vehicle_key`, `repair`, aktueller Beschreibung, `errors={}`.

**Route POST** `/vehicles/{vehicle_key}/repairs/{repair_id}/edit`:
- Gleiche Auflösung/Validierung wie GET.
- `container.update_repair.execute(repair_id=rid, description=description.strip() or None)`.
- Redirect (303) auf `/vehicles/{canonical_key}`.

**`edit_repair.html`** (analog `edit_vehicle.html`):
- Formular mit `description`-Textarea (vorbefüllt), Datum als read-only-Anzeige.
- Speichern-Button + Abbrechen-Link zurück zur Detailseite.
- Link "Fotos hochladen" auf den bestehenden Upload-Flow (`/vehicles/{key}/repairs/{id}/upload`).

**`vehicle_detail.html`:** pro Reparatur-Karte einen "Bearbeiten"-Link neben "Bilder hochladen".

**`container.py`:** Feld `update_repair: UpdateRepairUseCase` ergänzen, mit `UpdateRepairUseCase(repair_repo)` verdrahten.

---

## Nicht-Ziele (bewusst)

- **Datum ändern** — bleibt unveränderlich; kein Ordner-Umbenennen/Verschieben von Fotos.
- **`repairs.folder_name`-Konsistenz** — nach einem Edit weicht der Index-Wert kosmetisch vom echten Ordner-Slug ab. Da die Spalte nirgends gelesen wird, out of scope.
- **Reparatur löschen** — nicht Teil dieses Features.
- **Beschreibung durchsuchbar machen** — Reparatur-Beschreibung bleibt (wie heute) nicht Teil der Suche.

---

## Fehlerbehandlung

| Fall | Verhalten |
|------|-----------|
| Unbekanntes Fahrzeug (`vehicle_key`) | 404 |
| `repair_id` kein gültiges ULID | 404 |
| Reparatur nicht vorhanden (`RepairNotFound`) | 404 |
| Reparatur gehört nicht zum Fahrzeug | 404 |
| Leere/Whitespace-Beschreibung | Gültig → wird zu `None` (Reparatur "ohne Beschreibung") |

---

## Testing

- **Unit `UpdateRepairUseCase`** (`tests/application/`):
  - Aktualisiert die Beschreibung; `id`, `vehicle_id`, `date`, `created_at` bleiben unverändert.
  - Whitespace-only / leer → `description is None`.
  - `RepairNotFound` propagiert bei unbekannter ID.
- **Presentation** (`tests/presentation/`):
  - GET Edit-Formular rendert die aktuelle Beschreibung.
  - POST aktualisiert und liefert 303-Redirect auf die Fahrzeug-Detailseite.
  - 404-Fälle (unbekanntes Fahrzeug, unbekannte/fremde Reparatur, ungültige ID).
- **Regression `_handle_image`-Fix** (`tests/infrastructure/` bzw. Watcher-Tests): Nach einer Beschreibungsänderung (Ordner unverändert) wird ein neu hochgeladenes Foto weiterhin korrekt einer Reparatur zugeordnet und indexiert. **Kern-Regressionstest dieses Features.**
