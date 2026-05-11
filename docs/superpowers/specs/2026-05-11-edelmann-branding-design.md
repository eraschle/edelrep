# Edelmann-Branding (Logo + Farben)

**Status:** Design — bereit für Plan
**Datum:** 2026-05-11
**Scope:** Visuelle Anpassung der Web-UI an die Markenidentität von `www.edelmannmotos.ch`. Keine funktionalen Änderungen, keine Domain-/Application-/Infrastructure-Änderungen.

---

## Ziel

Die App soll für Werkstatt-Mitarbeitende von Edelmann Motos sofort als Teil ihres Betriebs erkennbar sein. Dazu wird das Logo der Firma in die Navbar eingebunden und die Tailwind-Farb-Palette von kühlem Blau/Slate auf das warme Gold/Stone der Edelmann-Website umgestellt. Schriftart bleibt Inter (bewusste Entscheidung — konservativer als die Site-Fonts Playfair/Rubik).

## Nutzungs-Szenarien

- **Erstkontakt:** Eine Person, die die App nicht kennt, öffnet `/search` und sieht das Edelmann-Logo + die vertraute Gold-/Beige-Optik der Firmen-Website. Klare Zuordnung.
- **Browser-Tab-Identifikation:** Favicon zeigt das Edelmann-Symbol — die App ist im Tab-Mix anderer Werkstatt-Tools wiedererkennbar.
- **Konsistenz mit Print/Web:** Sortimentslisten, Reparatur-Belege etc. der Firma tragen dieselben Farb-Codes; die App passt zur visuellen Sprache.

---

## Entscheidungen aus Brainstorming

| Frage | Entscheidung |
|-------|--------------|
| Branding-Tiefe | Logo + Farben. Fonts bleiben Inter. |
| Logo-Hosting | Lokal, im Repo committed (kein Hotlink). |
| Logo-Hintergrund | Transparent (PNG mit RGBA, weisse Pixel → α=0). |
| Logo-Verarbeitung | Einmaliges Helper-Skript `scripts/download_edelmann_logo.py`, Output committet. |
| Navbar-Layout | Logo links (h=40 px), App-Name "edelrep" + "Hauptseite"-Untertitel bleiben rechts daneben. |
| Werkzeug-Icon-Square | Entfällt (Logo selbst trägt Identität). |
| App-Name | "edelrep" bleibt. |
| Tailwind-Mechanik | Arbitrary-Values `bg-[#b59775]` inline. Keine Custom-Tailwind-Config (CDN-Mode bleibt). |
| Semantische Farben | Amber/Green/Red für Warn/Success/Destruktiv bleiben unverändert. Status-Badges (uploading=blau, ok=grün, error=rot, pending=slate) bleiben funktional. |

---

## Brand-Quelle: `www.edelmannmotos.ch`

**Logo (Navbar-Bild):**
- URL: `https://files.designer.hoststar.ch/96/58/9658be91-e409-491c-8729-a8db54dcbe42.jpg`
- Alt-Text: "Zweirad Edelmann GmbH EdelmannMotos"
- Format: JPG, weisser Hintergrund

**Favicon:**
- URL: `https://files.designer.hoststar.ch/4d/12/4d12297c-e063-4950-80cd-49dab8c26b4a.ico`

**Farb-Palette (aus dem aktiven CSS extrahiert, sortiert nach Häufigkeit):**

| Hex | Verwendung | Tailwind-Pendant |
|-----|------------|------------------|
| `#252525` | Primärer Text/Foreground | nahe `text-stone-900` (`#1c1917`) |
| `#ffffff` | Backgrounds | `bg-white` |
| `#b59775` | Primärer Brand-Akzent (Gold) | Arbitrary-Value `[#b59775]` |
| `#ac8a64` | Gold dunkler (Hover) | Arbitrary-Value `[#ac8a64]` |
| `#c8b198` | Gold heller | Arbitrary-Value `[#c8b198]` |
| `#5c5c5c` | Sekundärtext | nahe `text-stone-500` (`#78716c`) |
| `#eaeaea` / `#ededed` / `#f2f2f2` | Warme Grautöne (Borders, Backgrounds) | `bg-stone-100` / `bg-stone-200` |

**Fonts (nicht übernommen):**
- Playfair Display (Serif, Headings)
- Rubik (Sans, Body)

→ App bleibt bei Inter (siehe Entscheidung oben).

---

## Architektur

Rein Presentation-Layer. Domain / Application / Infrastructure: unverändert.

```
Presentation
├─ app_factory.py           (StaticFiles mount für /static)
├─ static/                  [NEU]
│   ├─ edelmann-logo.png    (transparent, ~30 KB)
│   └─ favicon.ico
└─ templates/               (Tailwind-Klassen Find-and-Replace)
    ├─ base.html            (Navbar-Logo, Favicon-Link, Body-bg, Button)
    ├─ search.html
    ├─ _vehicle_search_results.html
    ├─ vehicle_detail.html  (inkl. Modal + Caption + Comment-Klassen)
    ├─ new_repair.html      (Form + JS-Banner-Klassen)
    ├─ upload_image.html    (Form + JS-Banner-Klassen)
    ├─ new_vehicle.html
    ├─ _image_picker.html   (Picker-Buttons, Textarea, Status-Badges)
    ├─ inbox.html
    └─ inbox_detail.html

scripts/
└─ download_edelmann_logo.py  [NEU, einmaliger Helper, idempotent]
```

---

## Logo-Verarbeitung

### Helper-Skript

`scripts/download_edelmann_logo.py`:

- Pure Python, nutzt `urllib.request` (kein neuer Dep) für den Download.
- Pillow ist bereits Projekt-Dependency (EXIF / Thumbnails). `Image.open(...).convert("RGBA")`.
- Pixel-Maske: `(r > 240) and (g > 240) and (b > 240)` → `alpha = 0`. Rest opak. Schwellwert 240 lässt anti-aliased Logo-Kanten weitgehend intakt, entfernt weisse Flächen sauber.
- Speichert nach `src/edelrep/presentation/static/edelmann-logo.png` mit `optimize=True`.
- Lädt zusätzlich das Favicon (binär, ohne Verarbeitung) nach `src/edelrep/presentation/static/favicon.ico`.
- Print: Original-Dimension, finale Dateigrösse — als Sanity-Check für die Person, die das Skript ausführt.

### Idempotenz

Skript darf wiederholt laufen ohne Schaden. Schreibt einfach Dateien neu. Wenn Edelmann das Logo auf der Website ändert, wird das Skript erneut ausgeführt und der neue Output committed.

### Ein/Mehrmaliger Lauf

**Einmaliger Lauf während Implementierung.** Output wird committed (PNG + ICO im Repo, jeweils kleiner als 50 KB). Damit:
- Kein Runtime-Netzwerk-Zugriff (LAN-only-Betrieb bleibt funktional).
- Bekannter, deterministischer Build (keine Drift, wenn die Edelmann-Site das Bild ändert).
- Schnelle `git pull`-Verbreitung des neuen Brandings.

---

## Static-Files-Mount

`src/edelrep/presentation/app_factory.py`:

Neue Imports:
```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles
```

Vor `return app` (oder nach den Router-Includes):
```python
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")
```

Verifikation: `GET /static/edelmann-logo.png` antwortet `200` mit `Content-Type: image/png`.

---

## Template-Änderungen

### `base.html`

**`<head>`** — Favicon-Link ergänzen (vor dem bestehenden Font-Preconnect):
```html
<link rel="icon" type="image/x-icon" href="/static/favicon.ico">
```

**Navbar** — Logo statt Wrench-Icon-Square. Der bestehende Link-Wrapper bleibt erhalten, nur das Inner-Markup ändert sich:
```html
<a href="/search" title="Zur Hauptseite"
   class="group flex items-center gap-3 px-3 py-2 -mx-3 rounded-lg hover:bg-stone-100 transition-colors">
  <img src="/static/edelmann-logo.png" alt="Edelmann Motos" class="h-10 w-auto">
  <span class="flex flex-col leading-tight">
    <span class="text-lg font-semibold tracking-tight">edelrep</span>
    <span class="text-xs text-stone-500 group-hover:text-stone-700 transition-colors flex items-center gap-1">
      {{ icon("home", "w-3 h-3") }} Hauptseite
    </span>
  </span>
</a>
```

**Body-Hintergrund:** `bg-slate-50` → `bg-stone-50`.

**Navbar-Border:** `border-slate-200` → `border-stone-200`.

**"+ Fahrzeug"-Button** rechts in der Navbar:
- `bg-blue-600 hover:bg-blue-700` → `bg-[#b59775] hover:bg-[#ac8a64]`

### Farb-Mapping (gilt für ALLE Templates)

| Aktuell | Neu | Wo |
|---|---|---|
| `bg-blue-600` | `bg-[#b59775]` | Primary buttons (Submit, "+ X", "Hochladen", "Anlegen", "Speichern") |
| `hover:bg-blue-700` | `hover:bg-[#ac8a64]` | dito Hover |
| `focus:ring-blue-500 focus:border-blue-500` | `focus:ring-[#b59775] focus:border-[#b59775]` | Inputs, Textareas, Suche |
| `text-blue-600` | `text-[#ac8a64]` | Inline-Links ("Bilder hochladen", "In neuem Tab öffnen") |
| `hover:text-blue-800` | `hover:text-[#8a6f4f]` | dito Hover |
| `hover:border-blue-300` | `hover:border-[#c8b198]` | Card-Hover-Border |
| `hover:ring-blue-400` | `hover:ring-[#b59775]` | Thumbnail-Hover |
| `bg-blue-50 text-blue-700 ring-blue-200` | unverändert | Status-Badge "uploading" (technischer Indikator) |
| `bg-slate-50` | `bg-stone-50` | Body-Hintergrund |
| `bg-slate-100` | `bg-stone-100` | Thumb-Placeholder, Navbar-Hover |
| `text-slate-900` | `text-stone-900` | Primärer Body-Text |
| `text-slate-700` | `text-stone-700` | Sekundärer Text |
| `text-slate-600` / `500` / `400` | `text-stone-600` / `500` / `400` | Captions, Meta |
| `border-slate-200` / `300` | `border-stone-200` / `300` | Card- und Input-Border |
| `ring-slate-200` | `ring-stone-200` | Subtile Ringe |
| `bg-amber-*` (Warn-Banner) | unverändert | Semantisch |
| `bg-green-*` (Success-Banner) | unverändert | Semantisch |
| `bg-red-*` / `text-red-*` (Destruktiv, Fehler) | unverändert | Semantisch |

### JS-Strings mit Tailwind-Klassen

`new_repair.html`, `upload_image.html`, `_image_picker.html`, `vehicle_detail.html` enthalten JS-Code, der Tailwind-Klassen als String konkateniert (z. B. `banner.classList.add('bg-amber-50', ...)`). Diese Stellen müssen ebenfalls remapped werden — Strings sind nicht weniger wichtig als Markup-Attribute.

### Status-Badges in `_image_picker.html`

Der `setStatusBadge`-Helper hat eine Klassen-Map:
```javascript
const map = {
  pending:   { ..., cls: 'bg-slate-100 text-slate-700 ring-slate-200' },
  uploading: { ..., cls: 'bg-blue-50 text-blue-700 ring-blue-200' },
  ok:        { ..., cls: 'bg-green-50 text-green-700 ring-green-200' },
  error:     { ..., cls: 'bg-red-50 text-red-700 ring-red-200' },
};
```

- `pending` → `bg-stone-100 text-stone-700 ring-stone-200` (warm-grau statt cool-grau)
- `uploading` bleibt blau (technischer Indikator — soll Aufmerksamkeit erregen, ist kein Branding)
- `ok` / `error` bleiben grün / rot (semantisch)

---

## Validierung & Edge Cases

### Logo-Transparenz

- Schwellwert 240 für "fast-weiss": Beleg durch Sichtprüfung beim Implementieren. Falls Logo am Rand sichtbar abgeschnittene Pixel zeigt: Schwellwert auf 230 senken, erneut generieren.
- Falls Logo dunkle Akzente auf hellgrauem Hintergrund hätte (nicht weiss): andere Algorithmen wären nötig. Erwartet ist klassisch Logo auf weiss — Sanity-Check beim ersten Lauf bestätigt das.

### Static-Pfad

- Path-Auflösung über `Path(__file__).parent / "static"` ist robust gegen `cwd`-Wechsel.
- Wenn Static-Dir fehlt (z. B. weil `download_edelmann_logo.py` nie lief): `StaticFiles` failed beim Mount. Im Plan wird das Skript daher VOR der Mount-Aktivierung ausgeführt; das Repo enthält die generierten Dateien.

### Browser-Caching

- Logo wird mit dem Standard-`StaticFiles`-Cache-Header bedient. Bei Logo-Änderung (re-run download script + commit) sehen User die alte Version, bis Browser-Cache abläuft. Pragmatisch akzeptabel — Logo ändert sich selten.

### Fallback wenn Logo fehlt

- `<img alt="Edelmann Motos">` sorgt für Text-Fallback bei 404. Kein zusätzlicher Code nötig.

---

## Test-Strategie

### Neue Tests

`tests/presentation/test_static_assets.py`:
- `GET /static/edelmann-logo.png` → 200, `Content-Type: image/png`.
- `GET /static/favicon.ico` → 200, `Content-Type` enthält `icon` oder `octet-stream`.
- `GET /static/nonexistent.png` → 404 (StaticFiles-Verhalten bestätigen).

`tests/presentation/test_base_template.py` (oder Erweiterung von `test_home.py`):
- Jede aufgerufene Seite (`/search`, `/vehicles/new`, `/vehicles/12345` nach Seed) enthält:
  - `<img src="/static/edelmann-logo.png"` im HTML.
  - `<link rel="icon"` mit Href auf `/static/favicon.ico`.

### Regression-Guard

`tests/presentation/test_no_blue_classes.py`:
- Lädt mehrere repräsentative Seiten (`/search`, `/vehicles/new`, ein Vehicle-Detail, `/inbox`, eine Repair-New-Seite, eine Upload-Seite).
- Sucht im gerenderten HTML nach `\bbg-blue-`, `\btext-blue-`, `\bring-blue-` (Regex auf Klassen-Boundary).
- Erlaubte Ausnahme: `bg-blue-50`, `text-blue-700`, `ring-blue-200` aus Status-Badge "uploading" (whitelisted).
- Schlägt fehl, wenn nicht-whitelisted Blue-Klassen verbleiben.

### Bestehende Tests

Alle ~553 Tests müssen grün bleiben. Templates rendern weiterhin valides HTML; CSS-Klassen sind nur strings im HTML — bestehende Assertions auf Inhalt/Status/Struktur bleiben gültig.

---

## Out-of-Scope

- Dark Mode oder Theme-Switcher.
- App-Name-Änderung (bleibt "edelrep").
- Logo-Animationen, Hover-Effekte aufs Logo, Splash-Screens.
- Loading-Spinner-Brand-Anpassung (animation bleibt aktueller `animate-spin-slow`).
- Custom Tailwind-Build mit Theme-Config (CDN-Mode bleibt).
- CSS-Variablen für Brand-Farben.
- Mehrsprachigkeit / FR-IT-Labels.
- Anpassung der Edelmann-Fonts (Playfair / Rubik) — App bleibt bei Inter.
- Erneuter Download bei Logo-Update auf Edelmann-Seite — manueller Re-Run des Skripts bei Bedarf.

---

## Risiken & Annahmen

- **Logo-URL stabil**: Wir verlassen uns darauf, dass Edelmann das aktuelle JPG für die Initial-Migration bereitstellt. Da Output committet wird, kein Runtime-Risiko.
- **Transparenz-Threshold**: 240 ist eine Annahme. Erste Generation muss visuell geprüft werden; bei Bedarf nachjustieren.
- **Tailwind-Arbitrary-Values im CDN-Mode**: funktionieren, weil `cdn.tailwindcss.com` JIT-mode default ist. Bestätigt durch bestehende `bg-amber-50`-Verwendung — also nichts Neues. Sollte CDN-Verhalten je ändern, wäre Custom-Build der nächste Schritt (separates Ticket).
- **Static-Files unter Reverse-Proxy**: TLS-Terminator (nginx/Caddy) leitet `/static/*` an die App weiter — wenn jemand statt dessen Static direkt servieren will, ist das eine Deploy-Konfig-Frage, nicht App-Code.
