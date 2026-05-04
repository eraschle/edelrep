# Reparatur anlegen mit gleichzeitigem Bild-Upload

**Status:** Design — bereit für Plan
**Datum:** 2026-05-04
**Scope:** `presentation`-Layer (Templates + Routen). Keine Änderung an Domain, Application oder Infrastructure.

---

## Ziel

Beim Anlegen einer Reparatur sollen direkt im selben Formular ein oder mehrere Bilder hochgeladen werden können, von Laptop, iOS und Android. Der bestehende Zwei-Schritt-Flow (erst Reparatur, dann separate Upload-Seite) entfällt für den Standard-Pfad; die separate Upload-Seite bleibt erhalten und wird auf dieselbe Komponente umgestellt, damit Bilder zu bestehenden Reparaturen weiterhin nachträglich hinzugefügt werden können.

## Nutzungs-Szenarien

1. **Mechaniker am Laptop in der Werkstatt:** Reparatur dokumentieren, mehrere Fotos vom NAS oder Desktop per Datei-Picker auswählen, einreichen.
2. **Mechaniker mit Tablet/Handy am Fahrzeug:** Reparatur erfassen, Fotos direkt mit der Kamera des Geräts machen oder aus der Galerie wählen, einreichen.
3. **Nachtrag:** Bilder zu einer früher angelegten Reparatur über die bestehende Upload-Seite ergänzen — gleiches UI wie beim Anlegen.

## Entscheidungen aus Brainstorming

| Frage | Entscheidung |
|-------|--------------|
| Submit-Reihenfolge | Reparatur zuerst, danach Bilder sequenziell mit Pro-Bild-Status (HTMX-frei, vanilla JS) |
| Mobile Capture | Zwei separate Buttons: "Foto aufnehmen" (`capture="environment"`) und "Bilder auswählen" (`multiple`) |
| Validierung | Client-seitige Vorprüfung (Typ, Grösse, Duplikate); Server bleibt Wahrheit |
| Limits | Max 25 MB pro Bild. Keine Obergrenze für Anzahl Bilder pro Reparatur. |
| Pflicht-Bild | Mind. 1 Bild Client-seitig Pflicht (Submit disabled bis erfüllt). Server lehnt bildlose Reparaturen **nicht** ab. |
| Bestehende Upload-Seite | Behalten und auf dieselbe Komponente umstellen |
| Vorschau | Thumbnails (`URL.createObjectURL`) + Dateiname + Grösse + Entfernen-Button pro Eintrag, kein Drag&Drop |

## Architektur

Keine neuen Domain- oder Application-Komponenten. Bestehende Use-Cases `CreateRepair` und `UploadImage` werden über die existierenden Endpunkte aufgerufen, die um eine JSON-Antwort-Variante erweitert werden.

### Datenfluss (mit JavaScript)

```
Browser                          Server
  |                                 |
  |--- POST /repairs (JSON) ----->  | CreateRepair.execute()
  |  <-- 201 {repair_id, ...} -----|
  |                                 |
  |--- POST /images (file 1) ---->  | UploadImage.execute()
  |  <-- 201 {image_id} -----------|  (UI: ok)
  |                                 |
  |--- POST /images (file 2) ---->  | UploadImage.execute()
  |  <-- 422 {error} --------------|  (UI: Fehler, Retry möglich)
  |                                 |
  | (alle fertig)                   |
  |--- redirect /vehicles/{reg} --->|
```

### Progressive Enhancement (ohne JavaScript)

Form submittet klassisch -> Server erstellt Reparatur -> Redirect auf Vehicle-Detail-Seite. Bilder können danach über die separate Upload-Seite ergänzt werden. Ein `<noscript>`-Hinweis im Formular erklärt diesen Pfad. Die Pflicht-Validierung "mind. 1 Bild" greift in diesem Modus nicht — bewusste Akzeptanz, weil der Nachreich-Pfad (E-Mail-Ingest, separate Upload-Seite) ohnehin existiert.

## Komponenten & Dateien

### Neu

- `src/edelrep/presentation/templates/_image_picker.html`
  Jinja2-Macro `image_picker(name, multiple=True, required=True, max_size_mb=25)`. Enthält:
  - Versteckter `<input type="file" multiple accept="image/*">` (Galerie-Picker, ohne `capture`).
  - Versteckter `<input type="file" accept="image/*" capture="environment">` (Kamera direkt, einzelne Aufnahme).
  - Zwei sichtbare Buttons "Foto aufnehmen" und "Bilder auswählen".
  - `<div>`-Container für Thumbnails.
  - `<template>`-Element als Klon-Vorlage pro Vorschau-Eintrag.
  - `<script>`-Block (vanilla JS, IIFE pro Picker-Instanz) mit Datei-Auswahl-, Validierungs-, Vorschau- und Upload-Logik.

### Geändert (Templates)

- `src/edelrep/presentation/templates/new_repair.html`
  Bindet das Macro ein. Form bekommt `id="repair-form"`. Ein Inline-Skript am Seitenende übernimmt die Submit-Orchestrierung (erst Repair-POST, dann Bild-POSTs in Schleife, dann Redirect). `<noscript>`-Hinweis am Formular-Anfang.

- `src/edelrep/presentation/templates/upload_image.html`
  Wird komplett auf das Macro umgestellt. Form-Action zeigt direkt auf den Image-Endpoint. Inline-Skript übernimmt die Bild-Upload-Schleife (kein Repair-Create-Schritt nötig).

### Geändert (Routen)

- `src/edelrep/presentation/routes/repairs.py` -> `create_repair`-Handler
  Content-Negotiation: bei `Accept: application/json` JSON-Antwort `{"repair_id": "<ulid>", "vehicle_url": "/vehicles/<reg>"}` mit Status 201. Sonst weiterhin 303 Redirect. Validierungsfehler (ungültiges Datum, VehicleNotFound) als JSON-Body `{"error": "..."}` mit passendem Status, falls Accept JSON ist.

- `src/edelrep/presentation/routes/images.py` -> `upload_image`-Handler
  Content-Negotiation analog: JSON-Antwort `{"image_id": "<ulid>"}` Status 201 oder Fehler `{"error": "..."}` mit 422/404.

### Unverändert

Domain-Layer, Application-Use-Cases, Infrastructure, alle bestehenden Tests dieser Schichten.

## Validierung & Edge Cases

### Client-seitige Validierung pro Datei (in dieser Reihenfolge)

1. **MIME-Type:** muss mit `image/` beginnen. Sonst Eintrag mit Status "Kein Bildformat".
2. **Grösse:** <= 25 MB. Sonst "Zu gross (X MB, max 25)".
3. **Duplikat:** Name und Grösse identisch zu bereits ausgewähltem Eintrag -> wird nicht hinzugefügt, kurzer Hinweis "Bereits ausgewählt".

### Submit-Button-Zustand

Disabled, solange (a) Beschreibung leer, (b) Datum leer/ungültig, oder (c) kein **valides** Bild im Picker ist. Während des Submit-Vorgangs disabled mit Label "Lade hoch…".

### Status-Badges pro Bild

`wartet` -> `lädt hoch…` -> `hochgeladen` oder `Fehler: <message>` (mit Retry-Button daneben).

### Submit-Orchestrierung (JS)

1. Repair-Create-Request senden. Bei Server-Fehler: Submit wieder aktivieren, Fehler im Form anzeigen, kein Bild-Upload.
2. Bei Erfolg: Bilder **sequenziell** hochladen.
3. Pro Bild: Status aktualisieren. Loop bricht **nicht** bei Fehlern ab.
4. Nach allen Bildern: Wenn keine Fehler -> Auto-Redirect auf Vehicle-Detail nach 800 ms. Wenn Fehler vorhanden -> Banner "Reparatur angelegt. X von Y Bildern hochgeladen. Du kannst fehlgeschlagene Bilder erneut versuchen oder zur Fahrzeug-Detailseite weitergehen." Kein Auto-Redirect.

### Edge Cases

- **Reload mitten im Upload:** Reparatur ist serverseitig bereits angelegt. Keine Auto-Recovery; User landet auf leerem Formular und kann via Detail-Seite Bilder nachreichen.
- **Repair-Create OK, alle Bilder fehlgeschlagen:** Reparatur ohne Bilder bleibt bestehen. Banner zeigt das transparent.
- **Ohne JS:** Klassischer Submit, Repair entsteht ohne Bilder, Redirect. `<noscript>`-Hinweis erklärt Nachreich-Pfad.

## Test-Strategie

### Server-Tests (`tests/presentation/`)

Erweiterungen, keine Regression bestehender Tests:

- `test_repairs_route.py`:
  - Bestehender 303-Redirect-Pfad bleibt grün (Regression-Schutz).
  - Mit `Accept: application/json`: 201 + Body enthält `repair_id` (ULID) und `vehicle_url`.
  - Validierungsfehler (ungültiges Datum) mit JSON-Accept -> JSON-Error-Body, Status 400.
- `test_images_route.py`:
  - Bestehender 303-Redirect-Pfad bleibt grün.
  - Mit `Accept: application/json`: 201 + Body `{"image_id": "..."}`.
  - MIME-/Grössen-Fehler mit JSON-Accept -> JSON-Error-Body, Status 422.

### E2E-Tests (Playwright, `tests/e2e/`)

- `test_create_repair_with_images.py`:
  - Happy Path: Fahrzeug anlegen -> "+ Reparatur" -> Description + Datum -> ein bzw. mehrere Bilder via `setInputFiles` hinzufügen -> Thumbnails sichtbar -> Submit -> Redirect auf Vehicle-Detail -> Reparatur mit Bildern sichtbar.
  - Negative: ein zu grosses Bild + ein gültiges -> nur das gültige geht durch, anderes bekommt Fehler-Badge im Picker.
- `test_image_picker_required.py`:
  - Description + Datum eingeben, keine Bilder -> Submit-Button bleibt disabled.

### Manueller Test-Pfad (in der Plan-PR-Beschreibung dokumentiert, nicht automatisiert)

- iOS Safari: "Foto aufnehmen" öffnet Kamera direkt. "Bilder auswählen" zeigt Galerie mit Mehrfachauswahl.
- Android Chrome: dito.
- Desktop: Beide Buttons immer sichtbar; auf Desktop fällt der Kamera-Button auf einen Datei-Dialog zurück (kein User-Agent-Sniffing).

## Out-of-Scope (V1 dieses Specs)

- HEIC/HEIF-Verarbeitung von iPhones (Pillow-Verhalten ungeprüft) — separates Ticket falls relevant.
- Drag & Drop von Dateien aus dem Datei-Explorer in den Picker.
- Drag & Drop zum Umsortieren der Reihenfolge im Picker.
- Client-seitige Bild-Verkleinerung vor Upload.
- Auto-Recovery bei Browser-Reload mitten im Upload.
- Auth/Login (LAN-only bleibt).
- Parallele statt sequenzielle Uploads.
- Server-seitige Pflicht für mind. 1 Bild (bewusst Client-only).
