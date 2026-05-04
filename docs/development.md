# Entwicklung

Workflow, Konventionen und Test-Strategie für Beiträge zu edelrep.

## Setup

Siehe [installation.md → Entwicklungs-Setup](installation.md#entwicklungs-setup).

```bash
git clone <repo-url> edelrep
cd edelrep
uv sync
uv run pytest      # 499 tests grün
```

## Tooling

| Tool | Zweck | Aufruf |
|---|---|---|
| **pytest** | Test-Runner | `uv run pytest` |
| **pytest-cov** | Coverage-Messung | `uv run pytest --cov=edelrep --cov-report=term-missing` |
| **hypothesis** | Property-Based Testing | (in Tests inline) |
| **pyright** | Statische Typprüfung | `uv run pyright` |
| **ruff check** | Linter | `uv run ruff check .` |
| **ruff format** | Formatter | `uv run ruff format` |
| **uv** | Paketmanager | `uv sync`, `uv add ...` |

Alle Tools laufen in unter 10 Sekunden auf einem normalen Laptop. Lokale Vor-Commit-Routine:

```bash
uv run ruff format
uv run ruff check . --fix
uv run pyright
uv run pytest
```

## Code-Konventionen

### Sprache

- **Code, Comments, Docstrings, Tests, JSON-Schemas**: Englisch.
- **UI-Labels (Templates, Strings, die Endnutzer sehen)**: Deutsch.
- **Diese Doku + PLAN.md**: Deutsch (mit gelegentlichem Englisch für Fachbegriffe).

### Stil

- Ruff-konfiguriert über [`ruff.toml`](../ruff.toml). Line-length 110.
- Domain-Exceptions ohne `Error`-Suffix (DDD-Konvention) — `ruff.toml` ignoriert dafür `N818`.
- `from __future__ import annotations` wird **nicht** benötigt (Python 3.13).
- Pyright-Konfiguration in [`pyrightconfig.json`](../pyrightconfig.json) — `standard` Mode mit verschärften Regeln.
- Datetime-Werte sind **immer timezone-aware** an Domain-Grenzen. `_require_aware` validiert das.
- Pfade als `pathlib.Path`, nie als rohe Strings mit `/`. Storage-Keys über `Path.as_posix()` (cross-platform).

### Architektur-Regeln

Verbindlich, durch CI-Guards in jeder Phase verifiziert:

1. **Domain importiert nichts** ausser `stdlib` + `python-ulid`.
2. **Application importiert nur aus Domain** (Ports + Entities + Exceptions).
3. **Infrastructure** darf Domain-Ports implementieren — nie Application/Presentation importieren.
4. **Presentation** darf Application + Domain importieren — nie Infrastructure direkt (immer über Container).
5. **Keine OS-spezifischen Pfade** im Source: kein `/tmp/`, kein `os.chmod`, kein `signal.pause`.

Verifikation:

```bash
# Domain
! grep -REn "fastapi|sqlalchemy|fsspec|pydantic|httpx|requests|PIL|pillow|sqlite3|watchdog|jinja2|uvicorn|starlette|imap_tools|apscheduler" src/edelrep/domain/

# Application
! grep -REn "fastapi|jinja2|uvicorn|starlette|httpx|imap_tools|apscheduler" src/edelrep/application/

# OS-Independence
grep -RE "/tmp/|/var/|os\.chmod|os\.symlink|flock|signal\.pause" src/edelrep/ tests/
```

Alle drei müssen leer sein.

## Test-Strategie

| Test-Typ | Speicherort | Tools | Beispiel |
|---|---|---|---|
| Unit (Domain) | `tests/domain/` | pytest, hypothesis | `test_vehicle_id.py` (regex property test) |
| Unit (Application) | `tests/application/` | pytest, in-memory Fakes | `test_upload_image.py` |
| Integration (Filesystem-Stores) | `tests/infrastructure/filesystem/` | pytest, `tmp_path` | `test_vehicle_store.py` |
| Integration (Storage Backends) | `tests/infrastructure/storage/` | pytest, parametrize | `test_local_filesystem.py`, `test_fsspec_backend.py` |
| Integration (Index) | `tests/infrastructure/index/` | pytest, `:memory:` SQLite | `test_sqlite_search_index.py`, Property-Test |
| Integration (Watcher) | `tests/infrastructure/watcher/` | pytest, real watchdog | 10s SLA Polling-Tests |
| End-to-End (Web) | `tests/presentation/` | pytest, FastAPI TestClient | `test_e2e_click_path.py` |
| E2E (Email) | `tests/application/test_ingest_email_e2e.py` | pytest, fake EmailInbox | DoD-Test |
| Performance | `tests/infrastructure/index/test_performance.py` | pytest, time.perf_counter | 1000-Fahrzeuge-FTS5 |

### Coverage-Ziele

- **Total ≥ 95%** (durch `fail_under = 95` in `pyproject.toml` erzwungen).
- **Pro neue Datei ≥ 90%**.
- Domain-Schicht aktuell 100%.
- Defensive Branches dürfen mit `# pragma: no cover` markiert werden, mit kurzer Begründung.

### TDD-Workflow

Jeder Task in den [Phasen-Plänen](superpowers/plans/) folgt diesem Muster:

1. Failing Test schreiben.
2. `uv run pytest <test_file>` — verifizieren, dass er rot ist (typischerweise `ModuleNotFoundError`).
3. Minimale Implementierung schreiben, bis der Test grün ist.
4. Alle Gates laufen lassen (`pyright`, `pytest`, `ruff`).
5. Commit mit klar formuliertem Commit-Message-Pattern (`feat(<scope>): ...`, `test(<scope>): ...`, `fix(<scope>): ...`).

## Domain-Driven Design

`src/edelrep/domain/` ist bewusst klein:

- **Entities** (`entities.py`): `Vehicle`, `Repair`, `Image`, `ImageSource`. Frozen dataclasses mit `slots=True`. Invarianten in `__post_init__` (timezone-aware, non-negative).
- **Value Objects** (`value_objects.py`): `VehicleId`. Frozen mit Regex-Validierung.
- **Exceptions** (`exceptions.py`): flache Hierarchie unter `DomainError`. Jede Exception trägt das auslösende Feld als Attribut.
- **Ports** (`ports/`): `typing.Protocol`s mit `@runtime_checkable`. Strukturelle Verträge.

Use Cases (Application) komponieren Domain-Ports und implementieren Geschäftsregeln. Sie sind framework-frei und I/O-frei testbar gegen In-Memory-Fakes.

## Phasen-Pläne und Plan-Diff

Jede Phase wurde nach einem detaillierten Plan implementiert. Die Pläne liegen in `docs/superpowers/plans/`:

- `2026-05-02-phase-1-skeleton-and-domain.md`
- `2026-05-02-phase-2-filesystem-persistence.md`
- `2026-05-03-phase-3-storage-backend.md`
- `2026-05-03-phase-4-use-cases.md`
- `2026-05-03-phase-5-sqlite-index.md`
- `2026-05-03-phase-6-live-index.md`
- `2026-05-03-phase-7-web-ui.md`
- `2026-05-03-phase-8-email-ingestion.md`
- `2026-05-03-phase-9-polish-deployment.md`

Jeder Plan enthält Goal, DoD, File Structure, TDD-Tasks mit exakten Code-Snippets, und Self-Review-Notizen.

Tags pro Phase (`phase-1-complete` … `phase-9-complete`) markieren das jeweilige Acceptance-Commit.

## Lokal die App testen

Es gibt zwei Wege, die App lokal zu sehen:

### A) Über die CLI (vollständige Integration)

```bash
uv run edelrep serve --storage-root ./storage --index-path ./index.db
```

Browser: <http://127.0.0.1:8080>. LiveIndex läuft, Watcher reagiert auf externe File-Operationen.

### B) Über pytest (E2E-Test)

```bash
uv run pytest tests/presentation/test_e2e_click_path.py -v
```

Führt den DoD-Klick-Pfad in 0.14 s durch (kein Webserver, nur `TestClient`).

## Eigene Use Cases / Adapter beitragen

1. Schreibe Test in `tests/application/` oder `tests/infrastructure/<scope>/`.
2. Verifiziere Failure.
3. Implementiere unter `src/edelrep/<scope>/`.
4. Aktualisiere `__init__.py` Re-Exports falls die neue Klasse Teil der öffentlichen API ist.
5. Aktualisiere Container (`presentation/container.py`), wenn die Komponente in der Produktion verdrahtet werden muss.
6. Aktualisiere ggf. die CLI (`cli/main.py`).
7. Commit-Message folgt Conventional Commits (`feat(<scope>):`, `test(<scope>):`, `refactor(<scope>):`, `fix(<scope>):`, `docs:`, `chore(deps):`).

## Versions-Bumps

Aktuell `__version__ = "0.1.0"` in `src/edelrep/__init__.py` und `version = "0.1.0"` in `pyproject.toml`. Beide synchron halten bei Bumps.

## Häufige Probleme

| Problem | Lösung |
|---|---|
| `pytest` zeigt mehr `ResourceWarning` | Hintergrund: einige Tests schliessen SQLite-Connections nicht. Bekannt; folgt in einem späteren Sweep. |
| `pyright` warnt über `reportMissingTypeStubs` für `fsspec` / `apscheduler` / `imap-tools` | Akzeptiert (Drittanbieter-Lib ohne Stubs). Ignoriert in `pyrightconfig.json`. |
| Coverage-Gate scheitert nach Refactor | `--cov-report=term-missing` zeigt fehlende Zeilen. Defensive Guards: `# pragma: no cover` mit Begründung. |
| watchdog-Test flakt auf macOS | Polling-Deadline auf 15 s erhöhen (FSEvents ~250ms Latenz). |
| Ruff `PLC0415` flag inline imports | Imports immer am File-Top platzieren. |

## Weiterführend

- [Architecture](architecture.md)
- [Configuration](configuration.md)
- [Installation](installation.md)
- [PLAN.md](../PLAN.md) — Architektur-Entscheidungen V1
