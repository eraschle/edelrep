# Edelmann-Branding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Web-UI visuell an die Markenidentität von `www.edelmannmotos.ch` angleichen — Logo lokal eingebunden, Tailwind-Palette von Blue/Slate auf Gold/Stone umgestellt.

**Architecture:** Rein Presentation-Layer. Statische Assets unter `src/edelrep/presentation/static/` (Logo PNG mit transparentem Hintergrund + Favicon ICO), via FastAPI `StaticFiles` an `/static` gemountet. Templates kriegen Find-and-Replace auf Tailwind-Klassen (inklusive JS-Strings). Domain / Application / Infrastructure: unverändert.

**Tech Stack:** FastAPI `StaticFiles`, Pillow (für Logo-Transparenz), Tailwind CDN (JIT-Mode mit Arbitrary-Values `[#b59775]`), `urllib.request` (stdlib, kein neuer Dep).

**Spec:** `docs/superpowers/specs/2026-05-11-edelmann-branding-design.md`

---

## File Structure

**Neue Dateien:**

- `scripts/download_edelmann_logo.py` — einmaliger Helper. Lädt das Original-JPG-Logo von der Edelmann-Site, ersetzt nahe-weisse Pixel durch Alpha=0, speichert als PNG. Lädt zusätzlich das Favicon-ICO unverändert. Idempotent.
- `src/edelrep/presentation/static/edelmann-logo.png` — Output des Helpers, committed.
- `src/edelrep/presentation/static/favicon.ico` — Output des Helpers, committed.
- `tests/presentation/test_static_assets.py` — Smoke-Tests für `/static/*`-Endpunkte und Brand-Element-Präsenz (Logo, Favicon-Link).
- `tests/presentation/test_branding_no_blue.py` — Regression-Guard, der nicht-whitelisted `bg-blue-` / `text-blue-` / `ring-blue-` / `bg-slate-` / `text-slate-` etc. in gerenderten Seiten verbietet.

**Geänderte Dateien:**

- `src/edelrep/presentation/app_factory.py` — Mount für `/static`.
- `src/edelrep/presentation/templates/base.html` — Favicon-Link, Navbar-Logo, Body-bg, "+ Fahrzeug"-Button.
- `src/edelrep/presentation/templates/search.html` — Such-Input.
- `src/edelrep/presentation/templates/_vehicle_search_results.html` — Trefferkarten.
- `src/edelrep/presentation/templates/vehicle_detail.html` — Vehicle-Card, Repair-Liste, Modal, Caption-Klassen (auch in JS-`classList.add/remove`).
- `src/edelrep/presentation/templates/new_repair.html` — Form, Submit-Button, JS-Banner-Klassen (`classList.add/remove`).
- `src/edelrep/presentation/templates/upload_image.html` — Form, Submit-Button, JS-Banner-Klassen.
- `src/edelrep/presentation/templates/new_vehicle.html` — Form, Submit-Button.
- `src/edelrep/presentation/templates/_image_picker.html` — Picker-Buttons, Comment-Textarea, Status-Badge-Klassen-Map im JS.
- `src/edelrep/presentation/templates/inbox.html` — Card-Border, Action-Links.
- `src/edelrep/presentation/templates/inbox_detail.html` — Card-Border, Action-Buttons.

**Bewusst weggelassen** (Spec-Out-of-Scope): Dark Mode, Theme-Switcher, App-Name-Änderung, Font-Umstellung auf Playfair/Rubik, Custom-Tailwind-Build, CSS-Variablen, Splash-Screens.

---

## Farb-Mapping-Referenz

Diese Tabelle ist die Vorlage für jeden Template-Task. Wo eine Zelle "unverändert" sagt, NICHT umstellen.

| Aktuell | Neu |
|---|---|
| `bg-blue-600` | `bg-[#b59775]` |
| `hover:bg-blue-700` | `hover:bg-[#ac8a64]` |
| `focus:ring-blue-500` | `focus:ring-[#b59775]` |
| `focus:border-blue-500` | `focus:border-[#b59775]` |
| `text-blue-600` | `text-[#ac8a64]` |
| `hover:text-blue-800` | `hover:text-[#8a6f4f]` |
| `hover:border-blue-300` | `hover:border-[#c8b198]` |
| `hover:ring-blue-400` | `hover:ring-[#b59775]` |
| `bg-slate-50` | `bg-stone-50` |
| `bg-slate-100` | `bg-stone-100` |
| `text-slate-900` | `text-stone-900` |
| `text-slate-700` | `text-stone-700` |
| `text-slate-600` | `text-stone-600` |
| `text-slate-500` | `text-stone-500` |
| `text-slate-400` | `text-stone-400` |
| `border-slate-200` | `border-stone-200` |
| `border-slate-300` | `border-stone-300` |
| `ring-slate-200` | `ring-stone-200` |
| `bg-blue-50 text-blue-700 ring-blue-200` (Status-Badge "uploading") | **unverändert** |
| `bg-amber-*` (Banner) | **unverändert** |
| `bg-green-*` (Banner) | **unverändert** |
| `bg-red-*` / `text-red-*` / `hover:bg-red-50` (Destruktiv) | **unverändert** |

---

## Task 1: Helper-Skript für Logo-Download + Transparenz

**Files:**
- Create: `scripts/download_edelmann_logo.py`

- [ ] **Step 1.1: Verzeichnis vorbereiten**

Run:
```bash
mkdir -p scripts src/edelrep/presentation/static
```

- [ ] **Step 1.2: Skript anlegen**

`scripts/download_edelmann_logo.py`:

```python
"""Einmaliger Helper: Logo + Favicon von edelmannmotos.ch laden, Logo
mit transparentem Hintergrund als PNG speichern.

Output:
    src/edelrep/presentation/static/edelmann-logo.png
    src/edelrep/presentation/static/favicon.ico

Re-run nach Marken-Update auf der Edelmann-Site — Output wird ins Repo
committed, kein Runtime-Netzwerk.
"""
from __future__ import annotations

import io
import urllib.request
from pathlib import Path

from PIL import Image

LOGO_URL = "https://files.designer.hoststar.ch/96/58/9658be91-e409-491c-8729-a8db54dcbe42.jpg"
FAVICON_URL = "https://files.designer.hoststar.ch/4d/12/4d12297c-e063-4950-80cd-49dab8c26b4a.ico"

STATIC_DIR = Path(__file__).resolve().parent.parent / "src" / "edelrep" / "presentation" / "static"
LOGO_OUT = STATIC_DIR / "edelmann-logo.png"
FAVICON_OUT = STATIC_DIR / "favicon.ico"

WHITE_THRESHOLD = 240  # Pixel mit r,g,b alle ≥ 240 → α=0


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 edelrep-branding-script"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def make_logo_transparent(raw: bytes) -> bytes:
    """Open the raw image bytes, mask near-white pixels to alpha=0, return PNG bytes."""
    src = Image.open(io.BytesIO(raw)).convert("RGBA")
    pixels = list(src.getdata())
    masked: list[tuple[int, int, int, int]] = []
    for r, g, b, a in pixels:
        if r >= WHITE_THRESHOLD and g >= WHITE_THRESHOLD and b >= WHITE_THRESHOLD:
            masked.append((r, g, b, 0))
        else:
            masked.append((r, g, b, a))
    out = Image.new("RGBA", src.size)
    out.putdata(masked)
    buffer = io.BytesIO()
    out.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def main() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading logo from {LOGO_URL}")
    raw_logo = _fetch(LOGO_URL)
    print(f"  raw {len(raw_logo)} bytes")
    transparent_png = make_logo_transparent(raw_logo)
    LOGO_OUT.write_bytes(transparent_png)
    with Image.open(LOGO_OUT) as written:
        size = written.size
    print(f"  saved {LOGO_OUT} ({len(transparent_png)} bytes, {size[0]}x{size[1]})")

    print(f"Downloading favicon from {FAVICON_URL}")
    favicon = _fetch(FAVICON_URL)
    FAVICON_OUT.write_bytes(favicon)
    print(f"  saved {FAVICON_OUT} ({len(favicon)} bytes)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 1.3: Smoke-Test der Transparenz-Funktion**

Inline-Test ohne Netz, validiert Pixel-Masking:

```bash
uv run python -c "
from PIL import Image
import io, sys
sys.path.insert(0, 'scripts')
from download_edelmann_logo import make_logo_transparent

src = Image.new('RGB', (4, 1), (255, 255, 255))
src.putpixel((0, 0), (0, 0, 0))
src.putpixel((1, 0), (250, 250, 250))
src.putpixel((2, 0), (200, 100, 50))
src.putpixel((3, 0), (245, 240, 239))
buf = io.BytesIO(); src.save(buf, format='JPEG'); raw = buf.getvalue()
out_bytes = make_logo_transparent(raw)
out = Image.open(io.BytesIO(out_bytes))
pixels = list(out.getdata())
print(pixels)
assert pixels[0][3] == 255, 'black must stay opaque'
assert pixels[1][3] == 0, 'near-white must be transparent'
assert pixels[2][3] == 255, 'mid-color must stay opaque'
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 1.4: Committen**

```bash
git add scripts/download_edelmann_logo.py
git commit -m "$(cat <<'EOF'
feat(branding): add helper to download Edelmann logo with transparency

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Helper ausführen + Logo committen

**Files:**
- Create: `src/edelrep/presentation/static/edelmann-logo.png` (Output)
- Create: `src/edelrep/presentation/static/favicon.ico` (Output)

- [ ] **Step 2.1: Helper laufen lassen**

Run:
```bash
uv run python scripts/download_edelmann_logo.py
```
Expected: Three "Downloading" / "saved" Zeilen ohne Exception. Output sollte Dateigrösse + Dimensionen zeigen (Logo 1200×~700 px erwartet, Favicon ~5–15 KB).

- [ ] **Step 2.2: Sichtprüfung Logo**

Run:
```bash
ls -la src/edelrep/presentation/static/
file src/edelrep/presentation/static/edelmann-logo.png
file src/edelrep/presentation/static/favicon.ico
```
Expected: `edelmann-logo.png` ist ein PNG mit Alpha-Channel (`PNG image data, ... 8-bit/color RGBA`), Favicon ist `MS Windows icon resource`.

Falls das PNG sichtbar Pixelreste am Rand hat (manuelle Inspektion mit Image-Viewer): `WHITE_THRESHOLD` in `download_edelmann_logo.py` von `240` auf `230` senken und Step 2.1 wiederholen. **Diese Anpassung ist im Plan, nicht im Skript zu fixen** — kein neuer Commit auf Task 1.

- [ ] **Step 2.3: Committen**

```bash
git add src/edelrep/presentation/static/edelmann-logo.png src/edelrep/presentation/static/favicon.ico
git commit -m "$(cat <<'EOF'
feat(branding): add Edelmann logo and favicon static assets

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: StaticFiles-Mount im app_factory

**Files:**
- Modify: `src/edelrep/presentation/app_factory.py`
- Create: `tests/presentation/test_static_assets.py`

- [ ] **Step 3.1: Failing Test schreiben**

`tests/presentation/test_static_assets.py`:

```python
from fastapi.testclient import TestClient


def test_logo_is_served(client: TestClient) -> None:
    r = client.get("/static/edelmann-logo.png")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")


def test_favicon_is_served(client: TestClient) -> None:
    r = client.get("/static/favicon.ico")
    assert r.status_code == 200
    ctype = r.headers["content-type"]
    assert "icon" in ctype or "octet-stream" in ctype or ctype.startswith("image/")


def test_missing_static_asset_returns_404(client: TestClient) -> None:
    r = client.get("/static/does-not-exist.png")
    assert r.status_code == 404
```

- [ ] **Step 3.2: Tests laufen — Fail erwartet**

Run: `uv run pytest tests/presentation/test_static_assets.py -v`
Expected: 3 Failures — `/static/*` ist nicht gemountet → 404 für Logo/Favicon (oder Logo-Test failt mit "image/png" mismatch je nach Default-Verhalten).

- [ ] **Step 3.3: StaticFiles im app_factory mounten**

In `src/edelrep/presentation/app_factory.py`:

Imports oben erweitern:
```python
from fastapi.staticfiles import StaticFiles
```

(`Path` ist bereits importiert.)

Neue Konstante neben `_TEMPLATES_DIR`:
```python
_STATIC_DIR = Path(__file__).parent / "static"
```

In `create_app` direkt nach den `app.include_router(...)`-Zeilen und vor `return app`:
```python
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
```

- [ ] **Step 3.4: Tests grün**

Run: `uv run pytest tests/presentation/test_static_assets.py -v`
Expected: 3 passed.

Run: `uv run pyright src/edelrep/presentation/ tests/presentation/` — 0 Errors.

- [ ] **Step 3.5: Committen**

```bash
git add src/edelrep/presentation/app_factory.py tests/presentation/test_static_assets.py
git commit -m "$(cat <<'EOF'
feat(branding): mount /static for logo and favicon assets

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: base.html — Logo, Favicon, Body-Theme

**Files:**
- Modify: `src/edelrep/presentation/templates/base.html`
- Modify: `tests/presentation/test_static_assets.py`

- [ ] **Step 4.1: Failing Tests für Logo + Favicon im Markup**

In `tests/presentation/test_static_assets.py` anhängen:

```python
def test_base_template_includes_favicon_link(client: TestClient) -> None:
    r = client.get("/search")
    assert r.status_code == 200
    assert '<link rel="icon"' in r.text
    assert "/static/favicon.ico" in r.text


def test_base_template_includes_logo_image(client: TestClient) -> None:
    r = client.get("/search")
    assert r.status_code == 200
    assert '<img src="/static/edelmann-logo.png"' in r.text
    assert 'alt="Edelmann Motos"' in r.text
```

- [ ] **Step 4.2: Tests laufen — Fail erwartet**

Run: `uv run pytest tests/presentation/test_static_assets.py -v`
Expected: 2 neue Failures, alte 3 grün.

- [ ] **Step 4.3: base.html ersetzen**

Komplettersatz von `src/edelrep/presentation/templates/base.html`:

```jinja
<!doctype html>
<html lang="de">
{%- from "_icons.html" import icon -%}
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}edelrep{% endblock %}</title>
  <link rel="icon" type="image/x-icon" href="/static/favicon.ico">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .animate-spin-slow { animation: spin 1.2s linear infinite; }
  </style>
</head>
<body class="bg-stone-50 text-stone-900 min-h-screen antialiased">
  <nav class="bg-white border-b border-stone-200 shadow-sm sticky top-0 z-10">
    <div class="max-w-4xl mx-auto px-6 py-3 flex justify-between items-center gap-4">
      <a href="/search"
         title="Zur Hauptseite"
         class="group flex items-center gap-3 px-3 py-2 -mx-3 rounded-lg hover:bg-stone-100 transition-colors">
        <img src="/static/edelmann-logo.png" alt="Edelmann Motos" class="h-10 w-auto">
        <span class="flex flex-col leading-tight">
          <span class="text-lg font-semibold tracking-tight">edelrep</span>
          <span class="text-xs text-stone-500 group-hover:text-stone-700 transition-colors flex items-center gap-1">
            {{ icon("home", "w-3 h-3") }} Hauptseite
          </span>
        </span>
      </a>
      <a href="/vehicles/new"
         class="inline-flex items-center gap-2 text-sm bg-[#b59775] hover:bg-[#ac8a64] text-white px-4 py-2.5 rounded-lg font-medium shadow-sm transition-colors">
        {{ icon("plus", "w-4 h-4") }} Fahrzeug
      </a>
    </div>
  </nav>
  <main class="max-w-4xl mx-auto px-6 py-8">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

- [ ] **Step 4.4: Tests grün**

Run: `uv run pytest tests/presentation/ -v`
Expected: alle grün (insb. die 5 in `test_static_assets.py`).

Run: `uv run pytest -x` (Volltest) — grün.

- [ ] **Step 4.5: Committen**

```bash
git add src/edelrep/presentation/templates/base.html tests/presentation/test_static_assets.py
git commit -m "$(cat <<'EOF'
feat(branding): Edelmann logo, favicon, and stone/gold theme in base.html

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: search.html + _vehicle_search_results.html

**Files:**
- Modify: `src/edelrep/presentation/templates/search.html`
- Modify: `src/edelrep/presentation/templates/_vehicle_search_results.html`

Reine String-Ersetzung gemäss Farb-Mapping. Keine neuen Tests — Such-Seiten haben bereits Tests, die Inhalt prüfen (nicht Tailwind-Klassen).

- [ ] **Step 5.1: search.html ersetzen**

Komplettersatz von `src/edelrep/presentation/templates/search.html`:

```jinja
{% extends "base.html" %}
{% from "_icons.html" import icon %}
{% block title %}Suche – edelrep{% endblock %}
{% block content %}
<h1 class="text-3xl font-bold mb-6 tracking-tight">Fahrzeug suchen</h1>
<div class="relative mb-6">
  <span class="absolute inset-y-0 left-0 pl-4 flex items-center text-stone-400 pointer-events-none">
    {{ icon("search", "w-5 h-5") }}
  </span>
  <input type="search"
         name="q"
         placeholder="Stammnummer, Rahmennummer oder Beschreibung – Tippfehler erlaubt"
         hx-get="/search/suggestions"
         hx-trigger="keyup changed delay:200ms, search"
         hx-target="#suggestions"
         class="w-full pl-12 pr-4 py-4 text-lg bg-white border border-stone-300 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-[#b59775] focus:border-[#b59775] transition-shadow">
</div>
<div id="suggestions">
  {% include "_vehicle_search_results.html" %}
</div>
{% endblock %}
```

- [ ] **Step 5.2: _vehicle_search_results.html ersetzen**

Komplettersatz von `src/edelrep/presentation/templates/_vehicle_search_results.html`:

```jinja
{% if results %}
<ul class="space-y-3">
{% for v in results %}
  <li>
    <a href="/vehicles/{{ v.id.registration_number }}"
       class="block bg-white border border-stone-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:border-[#c8b198] transition-all">
      <div class="text-xl font-semibold tracking-tight">{{ v.id.registration_number }}</div>
      {% if v.vin %}<div class="text-sm text-stone-600 mt-1">Rahmennummer: <span class="font-mono">{{ v.vin }}</span></div>{% endif %}
      {% if v.description %}<div class="text-sm text-stone-700 mt-1">{{ v.description }}</div>{% endif %}
    </a>
  </li>
{% endfor %}
</ul>
{% elif is_empty_filter %}
<p class="text-stone-500 text-center py-8">Keine Treffer.</p>
{% else %}
<p class="text-stone-500 text-center py-8">Noch keine Fahrzeuge angelegt.</p>
{% endif %}
```

- [ ] **Step 5.3: Tests grün**

Run: `uv run pytest tests/presentation/test_search.py -v`
Expected: alle grün.

- [ ] **Step 5.4: Committen**

```bash
git add src/edelrep/presentation/templates/search.html src/edelrep/presentation/templates/_vehicle_search_results.html
git commit -m "$(cat <<'EOF'
style(branding): apply stone/gold theme to search page and result list

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: vehicle_detail.html — Vehicle-Card, Modal, Caption (inkl. JS)

**Files:**
- Modify: `src/edelrep/presentation/templates/vehicle_detail.html`

- [ ] **Step 6.1: Datei aktuell lesen**

Run: `cat src/edelrep/presentation/templates/vehicle_detail.html`
(Zur Sicherheit, um genaue Zeilenkontexte zu sehen.)

- [ ] **Step 6.2: Template-Theme umstellen**

Im File die folgenden Klassen-Stellen ersetzen (Find-and-Replace, beachte Whole-Word):

| Suche | Ersetze durch |
|---|---|
| `border-slate-200` | `border-stone-200` |
| `text-slate-700` | `text-stone-700` |
| `text-slate-600` | `text-stone-600` |
| `text-slate-500` | `text-stone-500` |
| `text-slate-400` | `text-stone-400` |
| `border-slate-300` | `border-stone-300` |
| `border-dashed border-slate-300` | `border-dashed border-stone-300` |
| `bg-blue-600 hover:bg-blue-700` | `bg-[#b59775] hover:bg-[#ac8a64]` |
| `text-blue-600 hover:text-blue-800` | `text-[#ac8a64] hover:text-[#8a6f4f]` |
| `ring-1 ring-slate-200 hover:ring-[#b59775]` | (siehe unten — Thumbnails) |
| `ring-1 ring-slate-200` | `ring-1 ring-stone-200` |

Spezifische Stellen, die explizite Behandlung brauchen:

(a) **Thumbnail-Button hover-ring** — falls noch `hover:ring-blue-400` vorkommt: `hover:ring-[#b59775]`. (Im aktuellen Template ist es das `ring-1 ring-slate-200 hover:ring-blue-400` an `<button data-image-trigger>`.)

(b) **Modal-Submit-Button** — `bg-blue-600 hover:bg-blue-700` → `bg-[#b59775] hover:bg-[#ac8a64]`.

(c) **Textarea im Modal** — falls `focus:ring-...` vorhanden: ggf. `focus:ring-[#b59775]`. (Wenn keiner gesetzt ist: nicht ergänzen.)

(d) **Empty-State** — `bg-white border border-dashed border-slate-300 rounded-xl py-8` → `bg-white border border-dashed border-stone-300 rounded-xl py-8`.

- [ ] **Step 6.3: JS-classList-Aufrufe umstellen**

In `vehicle_detail.html`, im Modal-`<script>`-Block, die zwei Stellen:

Vorher:
```javascript
          caption.classList.remove('text-slate-400', 'italic');
          caption.classList.add('text-slate-600', 'line-clamp-2', 'break-words');
```

Nachher:
```javascript
          caption.classList.remove('text-stone-400', 'italic');
          caption.classList.add('text-stone-600', 'line-clamp-2', 'break-words');
```

- [ ] **Step 6.4: Verifizieren — keine slate/blue mehr in vehicle_detail.html**

Run: `grep -nE 'slate-|blue-' src/edelrep/presentation/templates/vehicle_detail.html`
Expected: keine Treffer.

- [ ] **Step 6.5: Tests grün**

Run: `uv run pytest tests/presentation/ -v`
Expected: alle grün, insbesondere `test_vehicle_detail_renders` und `test_vehicle_detail_modal_initially_hidden_without_flex_conflict`.

- [ ] **Step 6.6: Committen**

```bash
git add src/edelrep/presentation/templates/vehicle_detail.html
git commit -m "$(cat <<'EOF'
style(branding): stone/gold theme on vehicle detail + image modal + caption JS

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: new_repair.html — Form + JS-Banner-Klassen

**Files:**
- Modify: `src/edelrep/presentation/templates/new_repair.html`

- [ ] **Step 7.1: Template-Theme umstellen**

Folgende Ersetzungen im File durchführen (Find-and-Replace):

| Suche | Ersetze |
|---|---|
| `border-slate-200` | `border-stone-200` |
| `border-slate-300` | `border-stone-300` |
| `text-slate-700` | `text-stone-700` |
| `bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300` | `bg-[#b59775] hover:bg-[#ac8a64] disabled:bg-stone-300` |
| `focus:ring-blue-500 focus:border-blue-500` | `focus:ring-[#b59775] focus:border-[#b59775]` |

Banner-Klassen (`bg-amber-*`, `text-amber-*`, `border-amber-*`, `bg-green-*`, `text-green-*`, `border-green-*`) bleiben **unverändert** — semantische Farben.

`text-red-600` (Fehler-Text) und `bg-red-50 border-red-200` (Fehler-Box) bleiben **unverändert**.

- [ ] **Step 7.2: JS-classList-Aufrufe (Banner-Toggle) prüfen**

Im `<script>`-Block sind diese Stellen:

```javascript
      banner.classList.remove('bg-amber-50', 'text-amber-900', 'border-amber-200');
      banner.classList.add('bg-green-50', 'text-green-900', 'border-green-200');
      ...
      banner.classList.remove('bg-green-50', 'text-green-900', 'border-green-200');
      banner.classList.add('bg-amber-50', 'text-amber-900', 'border-amber-200');
```

Diese sind **unverändert** — semantische Banner-Farben.

- [ ] **Step 7.3: Verifizieren**

Run: `grep -nE 'slate-|blue-' src/edelrep/presentation/templates/new_repair.html`
Expected: keine Treffer.

- [ ] **Step 7.4: Tests grün**

Run: `uv run pytest tests/presentation/test_repairs.py tests/presentation/test_e2e_click_path.py -v`
Expected: alle grün.

- [ ] **Step 7.5: Committen**

```bash
git add src/edelrep/presentation/templates/new_repair.html
git commit -m "$(cat <<'EOF'
style(branding): stone/gold theme on new repair form

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: upload_image.html — Form + JS-Banner

**Files:**
- Modify: `src/edelrep/presentation/templates/upload_image.html`

- [ ] **Step 8.1: Template-Theme umstellen**

Folgende Ersetzungen im File:

| Suche | Ersetze |
|---|---|
| `border-slate-200` | `border-stone-200` |
| `border-slate-300` | `border-stone-300` |
| `bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300` | `bg-[#b59775] hover:bg-[#ac8a64] disabled:bg-stone-300` |
| `focus:ring-blue-500 focus:border-blue-500` | `focus:ring-[#b59775] focus:border-[#b59775]` (falls vorhanden) |

Banner-Klassen (amber/green) bleiben unverändert.

- [ ] **Step 8.2: JS-Banner-classList unverändert lassen**

Wie in Task 7 — die `classList.add/remove('bg-amber-*'/'bg-green-*', ...)`-Aufrufe sind semantische Banner-Farben und bleiben.

- [ ] **Step 8.3: Verifizieren**

Run: `grep -nE 'slate-|blue-' src/edelrep/presentation/templates/upload_image.html`
Expected: keine Treffer.

- [ ] **Step 8.4: Tests grün**

Run: `uv run pytest tests/presentation/test_images.py -v`
Expected: alle grün.

- [ ] **Step 8.5: Committen**

```bash
git add src/edelrep/presentation/templates/upload_image.html
git commit -m "$(cat <<'EOF'
style(branding): stone/gold theme on upload image form

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: new_vehicle.html — Form

**Files:**
- Modify: `src/edelrep/presentation/templates/new_vehicle.html`

- [ ] **Step 9.1: Template-Theme umstellen**

Folgende Ersetzungen:

| Suche | Ersetze |
|---|---|
| `border-slate-200` | `border-stone-200` |
| `border-slate-300` | `border-stone-300` |
| `text-slate-700` | `text-stone-700` |
| `bg-blue-600 hover:bg-blue-700` | `bg-[#b59775] hover:bg-[#ac8a64]` |
| `focus:ring-blue-500 focus:border-blue-500` | `focus:ring-[#b59775] focus:border-[#b59775]` |

`text-red-600` (Fehler) bleibt unverändert.

- [ ] **Step 9.2: Verifizieren**

Run: `grep -nE 'slate-|blue-' src/edelrep/presentation/templates/new_vehicle.html`
Expected: keine Treffer.

- [ ] **Step 9.3: Tests grün**

Run: `uv run pytest tests/presentation/test_vehicles.py -v`
Expected: alle grün.

- [ ] **Step 9.4: Committen**

```bash
git add src/edelrep/presentation/templates/new_vehicle.html
git commit -m "$(cat <<'EOF'
style(branding): stone/gold theme on new vehicle form

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: _image_picker.html — Macro + JS-Status-Badge-Map

**Files:**
- Modify: `src/edelrep/presentation/templates/_image_picker.html`

- [ ] **Step 10.1: Template-Block (HTML) umstellen**

Folgende Ersetzungen im Markup-Teil des Macros:

| Suche | Ersetze |
|---|---|
| `border-slate-200` | `border-stone-200` |
| `border-slate-300` | `border-stone-300` |
| `bg-slate-100` | `bg-stone-100` |
| `text-slate-900` | `text-stone-900` |
| `text-slate-600` | `text-stone-600` |
| `text-slate-500` | `text-stone-500` |
| `text-slate-400` | `text-stone-400` |
| `ring-slate-200` | `ring-stone-200` |
| `hover:bg-slate-50` | `hover:bg-stone-50` |

Picker-Trigger-Buttons ("Foto aufnehmen" / "Bilder auswählen") — die haben `bg-white hover:bg-slate-50 text-slate-900 border border-slate-300` → `bg-white hover:bg-stone-50 text-stone-900 border border-stone-300`.

Hint-Box (amber) bleibt **unverändert**.

Retry-Button (`text-blue-600 hover:text-blue-800`) → `text-[#ac8a64] hover:text-[#8a6f4f]`.

Remove-Button (`text-slate-400 hover:bg-red-50 hover:text-red-600`) → `text-stone-400 hover:bg-red-50 hover:text-red-600` (rot bleibt).

- [ ] **Step 10.2: JS-Status-Badge-Map umstellen**

Im IIFE-JS-Block die `setStatusBadge`-`map` updaten. Vorher:

```javascript
      const map = {
        pending:   { iconHtml: ICONS.clock,  label: 'wartet',       cls: 'bg-slate-100 text-slate-700 ring-slate-200' },
        uploading: { iconHtml: ICONS.loader, label: 'lädt hoch…',  cls: 'bg-blue-50 text-blue-700 ring-blue-200' },
        ok:        { iconHtml: ICONS.check,  label: 'hochgeladen',  cls: 'bg-green-50 text-green-700 ring-green-200' },
        error:     { iconHtml: ICONS.alert,  label: 'Fehler',       cls: 'bg-red-50 text-red-700 ring-red-200' },
      };
```

Nachher:

```javascript
      const map = {
        pending:   { iconHtml: ICONS.clock,  label: 'wartet',       cls: 'bg-stone-100 text-stone-700 ring-stone-200' },
        uploading: { iconHtml: ICONS.loader, label: 'lädt hoch…',  cls: 'bg-blue-50 text-blue-700 ring-blue-200' },
        ok:        { iconHtml: ICONS.check,  label: 'hochgeladen',  cls: 'bg-green-50 text-green-700 ring-green-200' },
        error:     { iconHtml: ICONS.alert,  label: 'Fehler',       cls: 'bg-red-50 text-red-700 ring-red-200' },
      };
```

(Nur `pending` ändert sich auf stone. `uploading` bleibt blau — Spec-Whitelist.)

- [ ] **Step 10.3: Verifizieren**

Run: `grep -nE 'slate-' src/edelrep/presentation/templates/_image_picker.html`
Expected: keine Treffer.

Run: `grep -nE 'blue-' src/edelrep/presentation/templates/_image_picker.html`
Expected: nur die drei `bg-blue-50`/`text-blue-700`/`ring-blue-200` aus der Status-Badge-Map für "uploading".

- [ ] **Step 10.4: Tests grün**

Run: `uv run pytest tests/presentation/ -v`
Expected: alle grün.

- [ ] **Step 10.5: Committen**

```bash
git add src/edelrep/presentation/templates/_image_picker.html
git commit -m "$(cat <<'EOF'
style(branding): stone/gold theme on image picker (incl. pending badge)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: inbox.html + inbox_detail.html

**Files:**
- Modify: `src/edelrep/presentation/templates/inbox.html`
- Modify: `src/edelrep/presentation/templates/inbox_detail.html`

- [ ] **Step 11.1: inbox.html — Ersetzungen**

| Suche | Ersetze |
|---|---|
| `border-slate-200` | `border-stone-200` |
| `border-slate-300` | `border-stone-300` |
| `text-slate-700` | `text-stone-700` |
| `text-slate-600` | `text-stone-600` |
| `text-slate-500` | `text-stone-500` |
| `text-slate-400` | `text-stone-400` |
| `bg-blue-600 hover:bg-blue-700` | `bg-[#b59775] hover:bg-[#ac8a64]` |
| `text-blue-600 hover:text-blue-800` | `text-[#ac8a64] hover:text-[#8a6f4f]` |
| `hover:border-blue-300` | `hover:border-[#c8b198]` |

Run: `grep -nE 'slate-|blue-' src/edelrep/presentation/templates/inbox.html`
Expected: keine Treffer.

- [ ] **Step 11.2: inbox_detail.html — Ersetzungen**

Dieselbe Mapping-Tabelle anwenden.

Run: `grep -nE 'slate-|blue-' src/edelrep/presentation/templates/inbox_detail.html`
Expected: keine Treffer.

- [ ] **Step 11.3: Tests grün**

Run: `uv run pytest tests/presentation/test_inbox.py -v`
Expected: alle grün.

- [ ] **Step 11.4: Committen**

```bash
git add src/edelrep/presentation/templates/inbox.html src/edelrep/presentation/templates/inbox_detail.html
git commit -m "$(cat <<'EOF'
style(branding): stone/gold theme on inbox pages

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Regression-Guard — keine ungewollten slate/blue-Klassen

**Files:**
- Create: `tests/presentation/test_branding_no_blue.py`

- [ ] **Step 12.1: Test schreiben**

`tests/presentation/test_branding_no_blue.py`:

```python
"""Regression: after the Edelmann re-brand, slate and blue Tailwind classes
must not reappear in rendered pages. The only exception is the upload
status badge that uses bg-blue-50/text-blue-700/ring-blue-200 to signal
an in-progress upload — these stay as a functional indicator."""
from __future__ import annotations

import re
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from ulid import ULID

from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.presentation.container import Container

ALLOWED_BLUE = {"bg-blue-50", "text-blue-700", "ring-blue-200"}

# A class name is e.g. "bg-blue-500", "text-blue-600", "ring-blue-200",
# "border-blue-300", "hover:bg-blue-700" (with `:` prefix segments).
_BLUE_RE = re.compile(r"(?:^|[\s:\"'])((?:bg|text|ring|border|fill|stroke)-blue-\d+)\b")
_SLATE_RE = re.compile(r"(?:^|[\s:\"'])((?:bg|text|ring|border|fill|stroke)-slate-\d+)\b")


def _find_blue(text: str) -> set[str]:
    return {m.group(1) for m in _BLUE_RE.finditer(text)} - ALLOWED_BLUE


def _find_slate(text: str) -> set[str]:
    return {m.group(1) for m in _SLATE_RE.finditer(text)}


def _seed_full(container: Container) -> None:
    """Create one vehicle + one repair so the detail page is non-trivial."""
    vehicle = Vehicle(
        id=VehicleId("12345"), vin="WDB1", description="Kran",
        created_at=datetime.now(UTC),
    )
    container.vehicle_repo.save(vehicle)
    container.repair_repo.save(Repair(
        id=ULID(), vehicle_id=vehicle.id, date=date(2026, 5, 11),
        description="brakes", created_at=datetime.now(UTC),
    ))
    container.projector.full_rebuild(container.vehicle_repo, container.repair_repo, container.image_repo)


@pytest.mark.parametrize(
    "path",
    [
        "/search",
        "/vehicles/new",
        "/vehicles/12345",
        "/vehicles/12345/repairs/new",
        "/inbox",
    ],
)
def test_page_has_no_disallowed_blue_or_slate_classes(
    client: TestClient, container: Container, path: str
) -> None:
    _seed_full(container)
    r = client.get(path)
    assert r.status_code == 200, f"{path} returned {r.status_code}"
    bad_blue = _find_blue(r.text)
    bad_slate = _find_slate(r.text)
    assert not bad_blue, f"{path} has disallowed blue classes: {sorted(bad_blue)}"
    assert not bad_slate, f"{path} has disallowed slate classes: {sorted(bad_slate)}"
```

- [ ] **Step 12.2: Test laufen — sollte grün sein**

Run: `uv run pytest tests/presentation/test_branding_no_blue.py -v`
Expected: 5 passed. Falls Failures: das ist genau der Sinn — der Guard hat eine vergessene Stelle gefunden. Stelle finden via Path und ergänzen, Test laufen lassen.

- [ ] **Step 12.3: Volltest**

Run: `uv run pytest`
Expected: alle grün.

- [ ] **Step 12.4: Committen**

```bash
git add tests/presentation/test_branding_no_blue.py
git commit -m "$(cat <<'EOF'
test(branding): regression guard against re-introducing blue/slate classes

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Final Quality Gates

**Files:** keine Änderungen (Cleanup, falls nötig)

- [ ] **Step 13.1: Volle Test-Suite mit Coverage**

Run: `uv run pytest --cov=edelrep`
Expected: alle Tests grün, Coverage ≥ 95 %.

- [ ] **Step 13.2: Pyright**

Run: `uv run pyright`
Expected: 0 Errors.

- [ ] **Step 13.3: Ruff**

Run: `uv run ruff check . --fix && uv run ruff format .`
Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean.

Falls Auto-Fix Änderungen produziert hat, committen:

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore(branding): ruff format pass after re-theme

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Andernfalls überspringen.

- [ ] **Step 13.4: Domain & Application Import-Guards**

Run: `! grep -REn "fastapi|sqlalchemy|fsspec|jinja2|uvicorn|httpx|pillow|watchdog|apscheduler|imap_tools|rapidfuzz" src/edelrep/domain/`
Expected: exit 0 (keine Treffer).

Run: `! grep -REn "fastapi|jinja2|uvicorn|httpx|pillow|watchdog|imap_tools|apscheduler|rapidfuzz" src/edelrep/application/`
Expected: exit 0.

(Branding-Änderungen liegen nur in Presentation — Guards müssen weiterhin grün sein.)

- [ ] **Step 13.5: Manueller Smoke-Test**

Run:
```bash
rm -f index.db index.db-shm index.db-wal
uv run edelrep serve --storage-root ./storage --index-path ./index.db &
SERVER_PID=$!
sleep 3
HTTP_SEARCH=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/search)
HTTP_LOGO=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/static/edelmann-logo.png)
HTTP_FAVICON=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/static/favicon.ico)
echo "search=$HTTP_SEARCH logo=$HTTP_LOGO favicon=$HTTP_FAVICON"
kill $SERVER_PID 2>/dev/null
wait 2>/dev/null
```
Expected: `search=200 logo=200 favicon=200`.

- [ ] **Step 13.6: Visuelle Sichtprüfung (Optional, vom Engineer manuell)**

Browser öffnen auf `http://127.0.0.1:8080/search`. Checken:
- Logo links in Navbar, ohne weissen Hintergrund-Block (Transparenz greift).
- Favicon im Browser-Tab sichtbar.
- "+ Fahrzeug"-Button Gold (`#b59775`), Hover etwas dunkler.
- Such-Input Border-Ring beim Fokus Gold.
- Trefferkarten Hover-Border in hellem Gold (`#c8b198`).
- Vehicle-Detail-Card und Reparatur-Cards in weiss mit warm-grauen Borders.
- Falls Bild mit Kommentar vorhanden: Caption unter Thumbnail in `text-stone-600`.

Sichtprüfung ist kein automatischer Test, nur Verifikation, dass die Werte sinnvoll wirken. Falls etwas markant abweicht — z. B. Threshold zu aggressiv und Logo-Kanten zerfressen — Helper neu laufen lassen (Task 2 Step 2.2) und committen.

---

## Notes for the implementing engineer

- **YAGNI:** Keine CSS-Variablen, keine Custom-Tailwind-Config, keine Font-Umstellung. Inline-Arbitrary-Values reichen.
- **TDD:** Tests existieren für `/static/*` (Task 3) und für Brand-Element-Präsenz (Task 4). Regression-Guard (Task 12) prüft Korrektheit der Find-and-Replace-Tasks.
- **Don't:**
  - amber/green/red-Banner umfärben (semantisch);
  - das `bg-blue-50` der "uploading"-Badge ändern (funktionaler Indikator);
  - schwarz-roten Remove-Button neu einfärben (rot ist destruktiv);
  - das App-Name-Wort "edelrep" durch "Edelmann" ersetzen.
- **Hinweis zu Pillow:** ist bereits Dependency, kein `uv add` nötig.
- **Bei Spec/Plan-Diff:** Spec gewinnt (`docs/superpowers/specs/2026-05-11-edelmann-branding-design.md`).
