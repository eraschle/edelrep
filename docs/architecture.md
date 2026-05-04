# Architektur

## Leitidee

> **Filesystem ist Source of Truth.** SQLite ist nur ein wegwerfbarer Index-Cache. Alles, was edelrep speichert, ist als Mensch lesbare JSON-Sidecars + Bilddateien in einer Ordnerstruktur abgelegt — Backup, Cloud-Sync und Storage-Migration funktionieren mit `cp -r` / `rsync` / Nextcloud, ohne dass die App davon weiss.

Diese Entscheidung wirkt sich auf alle Schichten aus.

- Daten sind ohne die App lesbar (Wartung, Audit, Notfall).
- Der Index lässt sich jederzeit aus dem Filesystem rekonstruieren (`edelrep reindex`).
- Cloud-Sync (Nextcloud, Dropbox) funktioniert ohne edelrep-spezifische Adapter.
- Migration zwischen Storage-Backends ist trivial.

## Schichten (Clean Architecture)

```
┌─────────────────────────────────────────────────────────┐
│  Presentation                                           │
│  src/edelrep/presentation/                              │
│  • FastAPI Routes, Jinja2 Templates                     │
│  • Composition Root: Container + build_container()      │
└──────────────────┬──────────────────────────────────────┘
                   │ DI
                   ▼
┌─────────────────────────────────────────────────────────┐
│  Application (Use Cases)                                │
│  src/edelrep/application/                               │
│  • UploadImageUseCase, CreateVehicleUseCase, ...        │
│  • IngestEmailUseCase, ReindexUseCase, ...              │
│  Reine Orchestrierung. Kein Framework-Code.             │
└──────────────────┬──────────────────────────────────────┘
                   │ benutzt Ports (Protocols)
                   ▼
┌─────────────────────────────────────────────────────────┐
│  Domain                                                 │
│  src/edelrep/domain/                                    │
│  • Entities: Vehicle, Repair, Image, ImageSource        │
│  • Value Objects: VehicleId                             │
│  • Exceptions: DomainError + Subklassen                 │
│  • Ports (Protocols): VehicleRepository, RepairRepo,    │
│    ImageRepo, StorageBackend, SearchIndex, EmailInbox   │
│  Pures Python. Keine Imports ausserhalb stdlib + ulid.  │
└──────────────────▲──────────────────────────────────────┘
                   │ Implementierungen
                   │
┌──────────────────┴──────────────────────────────────────┐
│  Infrastructure (Adapter)                               │
│  src/edelrep/infrastructure/                            │
│  • filesystem/    JSON-Sidecars + atomic writes         │
│  • storage/       LocalFilesystemBackend, FsspecBackend │
│  • index/         SQLite + FTS5 + Projector             │
│  • exif/          Pillow-Verarbeitung                   │
│  • search/        InMemorySearchIndex (dev/test)        │
│  • watcher/       watchdog + Debouncer + DriftDetector  │
│  • email/         imap-tools + APScheduler              │
└─────────────────────────────────────────────────────────┘
```

**Abhängigkeitsregel**: jede Schicht darf nur nach **innen** zeigen. Domain hat keine Imports aus Application/Infrastructure/Presentation. Application importiert nur aus Domain. Infrastructure und Presentation dürfen nach innen zeigen, aber nie miteinander koppeln (Presentation → Application → Domain; Infrastructure → Domain für Ports).

CI-Guards (im `Phase X acceptance`-Schritt) verifizieren das per `grep` über die Schicht-Verzeichnisse.

## Storage-Layout

Per [PLAN.md §6](../PLAN.md):

```
<storage_root>/
├── 12345/                                      # registration_number
│   ├── _vehicle.json                           # Vehicle-Sidecar
│   ├── 2026-04-15__bremsen-vorne/              # Repair = ISO-Datum + "__" + Slug
│   │   ├── _repair.json
│   │   ├── 0001_<ulid>.jpg                     # Originalbilder
│   │   ├── 0002_<ulid>.jpg
│   │   └── _thumbs/
│   │       ├── 0001_<ulid>.jpg
│   │       └── 0002_<ulid>.jpg
│   └── 2026-05-02__oelwechsel/
│       └── ...
├── 67890/...
└── _system/
    └── inbox/                                  # Nicht zugeordnete Mails
        └── 2026-05-01T0912_<ulid>/
            ├── _inbox.json
            ├── 0001_brake.jpg
            └── ...
```

Sidecar-Schemas (alle mit `schema_version: 1`):

**`_vehicle.json`**
```json
{
  "schema_version": 1,
  "registration_number": "12345",
  "vin": "WDB12345...",
  "description": "Kran 4-achsig, Bj. 2018",
  "created_at": "2026-04-15T10:00:00+00:00"
}
```

**`_repair.json`**
```json
{
  "schema_version": 1,
  "id": "01J9TGZP6X2K0V3W7Y8Z4QABCD",
  "date": "2026-04-15",
  "description": "Bremsbeläge vorne erneuert",
  "created_at": "2026-04-15T16:30:00+00:00"
}
```

**`_inbox.json`**
```json
{
  "schema_version": 1,
  "message_id": "<...@example.com>",
  "from_address": "kunde@example.ch",
  "subject": "Stammnr 12345 Bremsen",
  "received_at": "2026-05-01T09:12:00+00:00",
  "status": "pending"
}
```

Pro Bild gibt es **keine** Sidecar-Datei in V1. Quelle (`manual` vs. `email`) und EXIF-Capture-Time werden beim Upload an die Use-Case übergeben, aber nicht persistiert — beim Lesen sind die Defaults `manual` / `None`.

## Ports & Adapter

| Port (`domain/ports/`) | Adapter (`infrastructure/`) |
|---|---|
| `VehicleRepository` | `FilesystemVehicleRepository` (filesystem/) |
| `RepairRepository` | `FilesystemRepairRepository` (filesystem/) |
| `ImageRepository` | `FilesystemImageRepository` (filesystem/) |
| `StorageBackend` | `LocalFilesystemBackend`, `FsspecBackend` (storage/) |
| `SearchIndex` | `SqliteSearchIndex` (index/), `InMemorySearchIndex` (search/) |
| `EmailInbox` | `ImapInbox` (email/) |

Die `ImageProcessor` Protocol ist in `application/upload_image.py` definiert (Application-Port) und wird von `PillowImageProcessor` (infrastructure/exif/) implementiert.

## Datenfluss am Beispiel: Bild hochladen

```
Browser → POST /vehicles/{reg}/repairs/{ulid}/images
        ↓
FastAPI Route (presentation/routes/images.py)
  ↓ ContainerDep injects
UploadImageUseCase (application/upload_image.py)
  ↓ 1. repair_repo.get(repair_id)              [→ raises RepairNotFound on miss]
  ↓ 2. processor.process(raw_bytes)            [→ EXIF rotation, Thumbnail, captured_at]
  ↓ 3. image_repo.save(image, raw_bytes=...,   [→ atomic write to <reg>/<dir>/NNNN_<ulid>.jpg]
  ↓                    thumbnail_bytes=...)    [→ + _thumbs/NNNN_<ulid>.jpg]
  ↓ 4. image_repo.get(image.id)                [→ re-read populated entity]
  ↓
Returns Image entity → 303 Redirect zur Vehicle-Detail-Seite

Asynchron (separater Thread):
  watchdog Observer sees the new file
  → KeyEventHandler maps path to storage key
  → Debouncer batches event (300ms window)
  → Flush calls SqliteIndexProjector.upsert_image(...)
  → SQLite-Index ist konsistent
```

## SQLite-Index

Schema in `src/edelrep/infrastructure/index/schema.sql`. Tabellen:

- `vehicles` (Primary key: `registration_number`) + `vehicles_fts` (FTS5 virtuelle Tabelle, externer Content)
- `repairs` (Primary key: `id` ULID) — für zukünftige JOIN-Queries
- `images` (Primary key: `id` ULID) — für zukünftige JOIN-Queries
- `meta` (`schema_version`, `last_full_reindex`)

FTS5-Trigger halten `vehicles_fts` synchron mit `vehicles`. Der Index wird beim Öffnen geprüft: bei Schema-Mismatch wird er destruktiv neu aufgebaut (Index = wegwerfbar, Filesystem = Wahrheit).

## Live-Index

`infrastructure/watcher/`:

```
LiveIndex.start():
  ├── DriftDetector.is_drifted()  → boolean (wird im UI als Banner gezeigt)
  └── Observer.schedule(KeyEventHandler, storage_root, recursive=True)

watchdog Event → KeyEventHandler.on_any_event:
  ├── filtert .tmp.<hex> Atomic-Writes
  ├── filtert _thumbs/ (kein Index-Update nötig)
  ├── filtert IGNORED keys
  └── Debouncer.add(key)

300ms später: Debouncer flush:
  ├── für jeden Key: classify(key) → VEHICLE/REPAIR/IMAGE
  ├── liest Domain-Entity aus dem Repo (oder löscht, wenn Datei fehlt)
  └── ruft Projector.upsert_*/remove_* auf
```

OS-spezifische Backend-Auswahl (inotify / FSEvents / ReadDirectoryChangesW) erfolgt automatisch durch `watchdog`.

## E-Mail-Ingestion

`infrastructure/email/` + `application/ingest_email.py`:

```
APScheduler tick (alle 300s):
  IngestEmailUseCase.execute(limit=50):
    ImapInbox.fetch_unread()                   [→ list[EmailMessage]]
    Pro Message:
      attachments = filter(image/* + size ≤ max_attachment_mb)
      reg_no = EmailSubjectParser.extract_registration_number(message)
      if reg_no fehlt OR ungültig OR Vehicle existiert nicht:
        InboxStore.park(message)               [→ _system/inbox/<slot>/]
      elif keine Attachments übrig:
        skip (mark_processed)
      else:
        try CreateRepairUseCase.execute(...)
        except DuplicateRepair: existierenden Repair via list_for_vehicle finden
        für jedes Attachment: UploadImageUseCase.execute(source=EMAIL)
      ImapInbox.mark_processed(message_id)     [→ \\Seen flag]
```

Das Passwort wird nie in der TOML-Konfiguration gespeichert — nur der Name einer Umgebungsvariable (`password_env = "EMAIL_PASSWORD"`).

## Web-UI

Server-rendered Jinja2 Templates mit Tailwind CSS und HTMX (beide via CDN). Keine JS-Build-Pipeline.

Templates unter `src/edelrep/presentation/templates/`:

- `base.html` — Layout (Navbar, Tailwind+HTMX `<script>`-Tags)
- `search.html` — Suchseite mit HTMX live-suggestions
- `_vehicle_search_results.html` — HTMX Partial für Suchergebnisse
- `vehicle_detail.html` — Fahrzeug-Detail mit Reparatur-Liste und Thumbnails
- `new_vehicle.html`, `new_repair.html`, `upload_image.html` — Formulare
- `inbox.html`, `inbox_detail.html` — Posteingang

Alle UI-Labels in Deutsch, abgebildet aus `presentation/labels.py` (per [PLAN.md §11.4](../PLAN.md)).

## CLI

`src/edelrep/cli/main.py` — argparse-basiert. Vier Subkommandos:

| Subkommando | Zweck |
|---|---|
| `serve` | uvicorn + LiveIndex (+ optional E-Mail-Poller über `--email-config`) |
| `watch` | Nur LiveIndex (kein Web-Server). Ctrl-C-tauglich. |
| `reindex` | SQLite-Index aus dem Filesystem neu bauen, dann beenden. |
| `migrate-storage` | `shutil.copytree` von `--from` nach `--to` mit Verifikation. |

Alle Subkommandos sind Cross-Platform — `signal.pause()` wird vermieden, `threading.Event().wait()` wird verwendet.

## Quality Gates

Jede der 9 Phasen hat einen formalen Acceptance-Schritt:

1. `uv run pyright` — 0 Errors
2. `uv run pytest --cov=edelrep` — alle Tests grün, Coverage ≥ 95% gesamt, ≥ 90% pro neue Datei (`fail_under = 95` in pyproject.toml)
3. `uv run ruff check . && ruff format --check .` — clean
4. Domain-Import-Guard: `! grep -REn "fastapi|sqlalchemy|fsspec|...|imap_tools|apscheduler" src/edelrep/domain/`
5. Application-Import-Guard: `! grep -REn "fastapi|jinja2|uvicorn|...|imap_tools|apscheduler" src/edelrep/application/`
6. OS-Independence-Guard: `grep -RE "/tmp/|/var/|os\.chmod|os\.symlink|flock|signal\.pause" src/ tests/`

Diese Guards halten die Architekturschichten sauber.

## Phasen-Plan

Detaillierte Implementierungs-Pläne pro Phase: [`superpowers/plans/`](superpowers/plans/). Jeder Plan enthält:

- Goal, Architecture, DoD
- File Structure (Created / Modified)
- Tasks mit TDD-Schritten und exakten Code-Snippets
- Self-Review-Notizen

## Weiterführende Doku

- [Installation](installation.md)
- [Configuration](configuration.md)
- [Development](development.md)
- [Backup & Recovery](backup.md)
- [Deployment](../deploy/README.md)
- [PLAN.md](../PLAN.md) — ursprünglicher Phasen-Plan
