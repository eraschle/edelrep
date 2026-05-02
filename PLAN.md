# Projekt-Plan: Fahrzeug-Bilder & Reparatur-Verwaltung

> **Architektur-Leitidee**: Das **Dateisystem ist Source of Truth**. Eine **SQLite-DB existiert nur als wegwerfbarer Index-Cache**, der jederzeit aus den Ordnern rekonstruiert werden kann. Damit bleiben Backup, Cloud-Sync und Storage-Migration trivial (`cp -r` reicht), während Suche und Listing trotzdem schnell sind.
>
> **Sprach-Konvention**: Code, Schemas und Konfig in **Englisch**. UI-Labels in **Deutsch**. Mapping passiert ausschliesslich in den Jinja-Templates.
>
> Dieser Plan ist so aufgebaut, dass er phasenweise an Claude Code übergeben werden kann. Jede Phase hat klare Akzeptanzkriterien.

---

## 1. Vision in einem Satz

Eine kleine, lokal betriebene Web-App, die Fahrzeugbilder in einer **menschenlesbaren Ordnerstruktur** ablegt, mit einem optionalen SQLite-Index für Performance — austauschbarer Storage (lokal, extern, Cloud), minimaler Bedien-Overhead, deutsches UI.

---

## 2. Geklärte Rahmenbedingungen für V1

| Thema | Entscheidung V1 |
|-------|-----------------|
| Auth / Login | **Keine** — LAN-only, Login später nachrüstbar |
| Mandantenfähigkeit | **Eine** Werkstatt, ein Storage-Root |
| Audit-Log | Nicht in V1 (über Sidecar-History später möglich) |
| Datenschutz / Aufbewahrung | **Daten bleiben dauerhaft** erhalten, kein Lösch-Workflow |
| Backup | Manuell — als **späteres Feature** vorgemerkt |
| UI-Sprache | **Deutsch** only |
| Code / SQL / Schema-Sprache | **Englisch** durchgehend |
| ID-Format Reparaturen | **ULID** (sortable, zeitbasiert) |
| Quelle pro Bild | aus Inbox-Eintrag ableiten, sonst `manual` |

---

## 3. Funktionale Anforderungen (Use Cases)

| ID | Use Case | Akteur |
|----|----------|--------|
| UC-01 | Bilder manuell hochladen (Drag & Drop oder Datei-Picker), Fahrzeug zuordnen | Werkstatt-User |
| UC-02 | Bilder via E-Mail empfangen, Anhänge automatisch dem korrekten Fahrzeug zuordnen | System |
| UC-03 | Fahrzeug suchen (Stamm- oder Rahmennummer, Teilstring) | Werkstatt-User |
| UC-04 | Alle Reparaturen eines Fahrzeugs chronologisch anzeigen | Werkstatt-User |
| UC-05 | Bilder einer Reparatur als Galerie ansehen, Original herunterladen | Werkstatt-User |
| UC-06 | Neues Fahrzeug anlegen (Stamm-/Rahmennummer + optionale Bezeichnung) | Werkstatt-User |
| UC-07 | Reparatur anlegen / bearbeiten | Werkstatt-User |
| UC-08 | Storage-Backend wechseln (Migration via `cp -r` + Reindex) | Admin |
| UC-09 | Index aus dem Filesystem neu aufbauen (`reindex` CLI) | Admin |

---

## 4. Nicht-funktionale Anforderungen

- **Filesystem-First**: Daten müssen ohne App lesbar bleiben.
- **Index ist Cache**: Löschen, neu bauen, fertig. Niemals zwingend.
- **Cloud-Sync-tauglich**: Nextcloud / Dropbox / OneDrive auf den Storage-Ordner zeigen lassen.
- **Storage-Agnostik**: Lokaler Pfad, externer HDD-Mount, S3 oder WebDAV.
- **SOLID + Clean Architecture**: Domain → Application → Infrastructure → Presentation.
- **Testbar**: Domain und Application zu 100% ohne I/O testbar.
- **Einfache Bedienung**: keine Fachterminologie im UI, grosse Klick-Targets, mobil benutzbar.

---

## 5. Tech-Stack

| Schicht | Wahl | Begründung |
|---------|------|------------|
| Sprache | Python 3.12+ | Standard im Workflow |
| Web-Framework | FastAPI | async, OpenAPI, gute DX |
| UI | Server-rendered Jinja2 + HTMX + TailwindCSS | kein Build-Schritt, mobile-tauglich |
| **Persistence (Truth)** | **JSON-Sidecar-Dateien neben den Bildern** | menschenlesbar, sync-tauglich |
| **Index-Cache** | **SQLite + FTS5, jederzeit reproduzierbar** | schnelle Suche |
| FS-Watcher | `watchdog` | hält Index live |
| Storage-Abstraktion | `StorageBackend`-Port, intern `fsspec` | deckt local, S3, WebDAV |
| Bilder | Pillow (Thumbnails, EXIF-Rotation) | Standard |
| E-Mail | `imap-tools` | angenehmer als `imaplib` |
| Validierung | Pydantic v2 | passt zu FastAPI |
| Hintergrund-Jobs | APScheduler (in-process) | reicht für E-Mail-Polling |
| ID-Generator | `python-ulid` | sortable, zeitbasiert |
| Dependency-Management | `uv` | schnell, lockfile |
| Lint / Format / Types | ruff, mypy --strict | wie gewohnt |
| Tests | pytest, pytest-asyncio, hypothesis | |

---

## 6. Datenmodell — die Ordnerstruktur

```
<storage_root>/
├── 12345/                                  # registration_number = Ordnername
│   ├── _vehicle.json                       # Vehicle-Metadaten
│   ├── 2026-04-15__bremsen-vorne/          # ISO-Datum + "__" + Slug (ASCII)
│   │   ├── _repair.json                    # Repair-Metadaten
│   │   ├── 0001_<ulid>.jpg                 # Originalbilder
│   │   ├── 0002_<ulid>.jpg
│   │   └── _thumbs/
│   │       ├── 0001_<ulid>.jpg
│   │       └── 0002_<ulid>.jpg
│   └── 2026-05-02__oelwechsel/
│       └── ...
├── 67890/
│   └── ...
└── _system/
    ├── inbox/                              # unzugeordnete E-Mails
    │   ├── 2026-05-01T0912_<ulid>.eml
    │   └── 2026-05-01T0912_<ulid>.json     # Inbox-Eintrag
    └── locks/                              # File-Locks für Background-Jobs
```

### Sidecar-Schemas

**`_vehicle.json`**
```json
{
  "registration_number": "12345",
  "vin": "WDB12345...",
  "description": "Kran 4-achsig, Bj. 2018",
  "created_at": "2026-04-15T10:00:00+02:00",
  "schema_version": 1
}
```

**`_repair.json`**
```json
{
  "id": "01J9TGZP6X2K0V3W7Y8Z4QABCD",
  "date": "2026-04-15",
  "description": "Bremsbeläge vorne erneuert",
  "created_at": "2026-04-15T16:30:00+02:00",
  "schema_version": 1
}
```

**Inbox-Eintrag `*.json`**
```json
{
  "message_id": "<...@example.com>",
  "from_address": "kunde@example.ch",
  "subject": "Stammnr 12345 Bremsen",
  "received_at": "2026-05-01T09:12:00+02:00",
  "status": "pending",
  "schema_version": 1
}
```

Pro Bild **keine** Sidecar-Datei — Quelle/Datum kommen aus EXIF + Inbox-Eintrag, sonst Default `manual`.

### Konventionen

- **registration_number** (Ordnername): `^[A-Za-z0-9._-]{1,64}$`
- **Reparatur-Slug**: ASCII, lowercase, max. 40 Zeichen, leere description → `"repair"`
- **Atomic Writes**: `tmp` schreiben + `os.replace`
- **`schema_version`** in jedem Sidecar — erlaubt zukünftige Migrationen

---

## 7. Architektur — Clean / Hexagonal

```
src/fahrzeugbilder/
├── domain/                       # Pures Python, keine Frameworks
│   ├── entities.py
│   ├── value_objects.py
│   ├── exceptions.py
│   └── ports/
│       ├── vehicle_repository.py
│       ├── repair_repository.py
│       ├── image_repository.py
│       ├── storage_backend.py
│       ├── search_index.py
│       └── email_inbox.py
│
├── application/                  # Use Cases
│   ├── upload_image.py
│   ├── search_vehicle.py         # benutzt SearchIndex
│   ├── list_repairs.py
│   ├── ingest_email.py
│   ├── reindex.py
│   ├── migrate_storage.py
│   └── dto.py
│
├── infrastructure/
│   ├── filesystem/               # Source of Truth
│   │   ├── vehicle_store.py
│   │   ├── repair_store.py
│   │   ├── image_store.py
│   │   ├── sidecar.py            # JSON-Read/Write, atomic, schema-aware
│   │   └── layout.py             # Pfad-Berechnung, Slug-Generierung
│   ├── index/                    # Cache
│   │   ├── sqlite_index.py
│   │   ├── schema.sql
│   │   ├── projector.py          # FS-Event → Index-Update
│   │   └── watcher.py            # watchdog-Integration
│   ├── storage/
│   │   ├── fsspec_backend.py
│   │   └── factory.py
│   ├── email/
│   │   ├── imap_inbox.py
│   │   └── parser.py
│   └── scheduler.py
│
├── presentation/
│   ├── api/
│   ├── web/
│   ├── templates/                # deutsche UI-Labels leben hier
│   └── static/
│
├── cli.py                        # reindex, migrate, doctor
├── config.py
└── main.py
```

### Datenfluss (ASCII)

```
   ┌─────────────────────┐         schreibt
   │   Use Case          │ ──────────────────► ┌──────────────────┐
   │   (z.B. Upload)     │                     │  Filesystem      │ ◄── Source of Truth
   └─────────┬───────────┘                     │  (JSON + Bilder) │
             │                                 └────────┬─────────┘
             │ liest direkt für ID-Lookup               │
             │                                          │ watchdog-Event
             ▼                                          ▼
   ┌─────────────────────┐  liest          ┌──────────────────────┐
   │   Use Case (Suche)  │ ───────────────►│  SQLite-Index-Cache  │
   └─────────────────────┘                 │  (FTS5, joins)       │
                                           └──────────────────────┘
                                                       ▲
                                                       │ rebuild
                                              ┌────────┴────────┐
                                              │  reindex CLI    │
                                              └─────────────────┘
```

**Kontrakt**: Bei Konflikt gewinnt das Filesystem. Kein Use Case darf Daten erzeugen, die *nur* im Index leben.

### Domain-Entities (Vorschau für Phase 1)

```python
# domain/value_objects.py
@dataclass(frozen=True)
class VehicleId:
    """Permanent Swiss vehicle registration number (Stammnummer)."""
    registration_number: str

# domain/entities.py
@dataclass
class Vehicle:
    id: VehicleId
    vin: str | None                  # Rahmennummer / chassis number
    description: str | None
    created_at: datetime

@dataclass
class Repair:
    id: ULID
    vehicle_id: VehicleId
    date: date
    description: str
    created_at: datetime

class ImageSource(StrEnum):
    MANUAL = "manual"
    EMAIL = "email"

@dataclass
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
    captured_at: datetime | None     # aus EXIF
```

---

## 8. Storage-Backends

Das Backend bestimmt, **wo das Root-Verzeichnis liegt**.

### Drei Modi

1. **Lokal** (default): `storage_root = /var/lib/fahrzeugbilder/data` oder `/mnt/usb_werkstatt/images`
2. **Cloud-Sync via Drittanbieter** (empfohlen): `storage_root` zeigt auf einen synchronisierten Ordner (Nextcloud-Client, Dropbox, OneDrive). Die App weiss nichts davon.
3. **Direkt-Remote via fsspec**: `storage_root = s3://bucket/...` oder `webdav://...`. Sidecar-Reads sind langsamer; lohnt nur, wenn der Index lokal liegt.

### Konfiguration

```toml
[storage]
mode = "local"                              # "local" | "fsspec"
root = "/var/lib/fahrzeugbilder/data"

# nur bei mode = "fsspec"
[storage.fsspec]
protocol = "s3"
options = { endpoint_url = "...", key = "...", secret_env = "S3_SECRET" }

[index]
path = "~/.cache/fahrzeugbilder/index.db"   # immer lokal, immer wegwerfbar
```

### Migration zwischen Backends

1. App stoppen
2. `rsync -a old_root/ new_root/`
3. `storage.root` umbiegen, App starten, `python -m fahrzeugbilder reindex`

Optional: `migrate_storage` Use Case mit Verifikation und Resume (für Cloud-Übergänge).

---

## 9. Index-Cache (SQLite)

### Schema

```sql
CREATE TABLE vehicles (
  registration_number  TEXT PRIMARY KEY,
  vin                  TEXT,
  description          TEXT,
  created_at           TEXT,
  fs_mtime             REAL              -- für Drift-Detection
);
CREATE INDEX idx_vehicles_vin ON vehicles(vin);

CREATE VIRTUAL TABLE vehicles_fts USING fts5(
  registration_number, vin, description,
  content='vehicles', content_rowid='rowid'
);

CREATE TABLE repairs (
  id                   TEXT PRIMARY KEY,    -- ULID
  registration_number  TEXT NOT NULL,
  date                 TEXT NOT NULL,
  description          TEXT,
  folder_name          TEXT NOT NULL,
  fs_mtime             REAL
);
CREATE INDEX idx_repairs_vehicle_date ON repairs(registration_number, date DESC);

CREATE TABLE images (
  id            TEXT PRIMARY KEY,           -- ULID
  repair_id     TEXT NOT NULL,
  filename      TEXT NOT NULL,
  thumb_path    TEXT,
  mime_type     TEXT,
  size_bytes    INTEGER,
  exif_taken_at TEXT,
  fs_mtime      REAL
);
CREATE INDEX idx_images_repair ON images(repair_id);

CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);
-- e.g. ('last_full_reindex', '2026-05-02T10:00:00+02:00')
```

### Befüllung

- **Voll-Reindex**: walk über `storage_root`, parse alle `_vehicle.json` und `_repair.json`, Bilder per `os.scandir`, Bulk-Insert in Transaktion. CLI: `fahrzeugbilder reindex [--dry-run]`.
- **Inkrementell**: `watchdog` beobachtet `storage_root`. Auf Created/Modified/Deleted → `Projector` aktualisiert betroffene Zeilen.
- **Drift-Check**: Beim Start vergleicht ein Selbsttest Stichprobe FS-mtime gegen `meta.last_full_reindex` — bei Abweichungen Hinweis-Banner im UI.

### Konsistenz-Garantie

> Das Filesystem ist die Wahrheit. Der Index ist optimierte Sicht.
> Bei Konflikt: Index wegwerfen, neu bauen.

Property-Test: zufällige FS-Operationen ausführen und am Ende `reindex` mit der live-projizierten Version vergleichen.

---

## 10. E-Mail-Ingestion

### Stammnummer-Erkennung

Parser sucht in dieser Reihenfolge:
1. Subject: `Stamm: 12345` / `Stammnr: 12345` / `#12345`
2. Erste Zeile des Bodys
3. Anhang-Dateiname beginnt mit Ziffern

Wenn nichts erkannt → Mail landet in `_system/inbox/` (`.eml` + `.json` mit `status="pending"`). UI zeigt Liste, User ordnet manuell zu.

### Polling

- APScheduler triggert alle 5 min
- IMAP via `imap-tools`, nur ungelesene Mails aus konfiguriertem Ordner
- Pro Mail: Anhänge filtern (`image/*`, max-Grösse) → `UploadImageUseCase` mit `source=ImageSource.EMAIL`
- Erfolgreich verarbeitet → IMAP-Flag `\Seen` + Label `processed`

### Konfiguration

```toml
[email]
enabled = true
host = "imap.example.com"
user = "werkstatt@..."
password_env = "EMAIL_PASSWORD"
folder = "INBOX"
poll_interval_seconds = 300
max_attachment_mb = 25
allowed_senders = ["*@firma.ch"]
```

---

## 11. UI-Konzept (Deutsch)

Drei Hauptscreens, optimiert für „grossflächiges Antippen":

### 11.1 Startseite — Suchen
- Riesiges Suchfeld: „Stammnummer oder Rahmennummer eingeben"
- Live-Vorschläge via HTMX (gegen Index)
- Darunter: 5 zuletzt geöffnete Fahrzeuge

### 11.2 Fahrzeug-Detail
- Kopf: Stammnummer, Rahmennummer, Bezeichnung
- Liste der Reparaturen (neueste oben), aufklappbar
- Pro Reparatur: Thumbnail-Strip, Klick = Galerie-Modal
- Button **„+ Bilder hochladen"** — gross, Drag-Drop und Datei-Picker

### 11.3 Posteingang
- Kachel pro ungeordneter Mail mit Vorschau
- Eingabefeld „Stammnummer", einklicken zum Zuordnen

### Design-Prinzipien
- Schriftgrösse ≥ 16px, Buttons ≥ 44px Höhe
- Maximal 2 primäre Aktionen pro Screen
- Bestätigungs-Toasts statt Pop-ups
- Index-Drift-Banner mit „Jetzt neu aufbauen"-Button (admin-sichtbar)

### Label-Mapping (Code → UI)

| Code-Identifier | UI-Label |
|-----------------|----------|
| `registration_number` | Stammnummer |
| `vin` | Rahmennummer |
| `description` (Vehicle) | Bezeichnung |
| `description` (Repair) | Beschreibung |
| `date` | Datum |
| `created_at` | Angelegt am |
| `uploaded_at` | Hochgeladen am |
| `source = manual` | Manuell |
| `source = email` | E-Mail |

---

## 12. Implementierungs-Phasen für Claude Code

Jede Phase = ein eigenständiger Claude-Code-Lauf. Pro Phase: Code + Tests + grünes `pytest`.

### Phase 1 — Skeleton & Domain
- Projektstruktur, `pyproject.toml`, `uv` setup
- Alle `domain/`-Entities, Value Objects, Exceptions (siehe Abschnitt 7)
- Alle `domain/ports/` als Protocols
- Unit-Tests für Domain-Invarianten (inkl. property-based für `VehicleId`)
- ✅ DoD: `mypy --strict` grün, Tests grün, **kein Framework** in `domain/`

### Phase 2 — Filesystem-Persistence (Source of Truth)
- `infrastructure/filesystem/`: layout, sidecar I/O, Repository-Implementierungen
- Atomic-Write-Helper (`tmp` + `os.replace`)
- Schema-Versions-Header in Sidecars
- Integration-Tests gegen `tmp_path`
- ✅ DoD: CRUD über echte Ordner; ein vorbereiteter Beispiel-Ordner wird korrekt eingelesen

### Phase 3 — Storage-Backend-Abstraktion
- `StorageBackend`-Port + `FsspecBackend`-Implementierung
- `Factory` aus Config
- Filesystem-Stores benutzen `StorageBackend` statt direkten `pathlib`-Zugriffs
- ✅ DoD: Stores funktionieren gegen lokales FS und gegen `memory://` von fsspec

### Phase 4 — Use Cases
- `UploadImageUseCase` (Thumbnail, EXIF-Rotation, Sidecar-Update)
- `ListRepairsUseCase`, `GetImageUseCase`
- `SearchVehicleUseCase` — vorerst gegen In-Memory-Fake des `SearchIndex`
- Application gegen Fakes der Ports
- ✅ DoD: Use Cases I/O-frei testbar; UploadImage erzeugt korrekte Ordnerstruktur

### Phase 5 — Index-Cache (SQLite)
- Schema, `SqliteSearchIndex` als `SearchIndex`-Implementierung mit FTS5
- `ReindexUseCase` + CLI `fahrzeugbilder reindex`
- `Projector` für inkrementelle Updates (manueller Aufruf, Watcher kommt in P6)
- Property-Test: zufällige FS-Operationen → finaler Index == reindex-Ergebnis
- ✅ DoD: Index aus FS reproduzierbar; Suche < 50 ms bei 1000 Fahrzeugen

### Phase 6 — Live-Index via FileWatcher
- `watchdog`-basierter Beobachter, hängt Projector an FS-Events
- Debouncing für Bulk-Operationen
- Drift-Detection beim Start, Banner-Trigger ans UI
- ✅ DoD: Datei extern reinkopieren → erscheint binnen 2 s in der Suche

### Phase 7 — Web-UI (HTMX, deutsche Labels)
- FastAPI-App, DI über `Depends`
- Suchseite, Fahrzeug-Detail, Upload-Form, Posteingang
- Tailwind via CDN reicht in V1
- E2E-Tests mit `httpx.AsyncClient`
- ✅ DoD: Klick-Pfad „neues Fahrzeug → Reparatur → Bilder hochladen → wiederfinden" geht durch

### Phase 8 — E-Mail-Ingestion
- `ImapInbox`-Adapter, `EmailSubjectParser`
- `IngestEmailUseCase`, APScheduler-Hookup
- Posteingang-UI
- ✅ DoD: Test-Mail mit Anhang wird verarbeitet, Bild erscheint am Fahrzeug

### Phase 9 — Polish & Deployment
- Storage-Migrations-CLI mit Verifikation
- Systemd-Unit oder Docker-Compose
- Backup-Doku (Storage-Ordner sichern, Index ist wegwerfbar)
- README mit Bildern für Endnutzer
- ✅ DoD: Frischer Mini-PC bootet die App in < 5 Min Setup

### Vorgemerkt für später (nicht V1)
- **Auth / Login** (z.B. fastapi-users)
- **Backup-Automation** (rclone-Schedule, Snapshot-Strategie)
- **Audit-Log** via Sidecar-History-Feld
- **Sidecar pro Bild** (`_image_<ulid>.json`) für reicheres Quelle-Tracking
- **Mehrsprachigkeit** (FR/IT)

---

## 13. Test-Strategie

| Schicht | Test-Typ | Tooling |
|---------|----------|---------|
| Domain | Unit, property-based | pytest, hypothesis |
| Application | Unit mit Fake-Ports | pytest |
| FS-Stores | Integration mit `tmp_path` | pytest |
| Index | **Property-Test: live-projector vs. full-reindex müssen identisch sein** | pytest, hypothesis |
| E-Mail-Parser | Tabellen-Tests | pytest.mark.parametrize |
| Web | E2E gegen TestClient | httpx |

Coverage-Ziel: Domain + Application ≥ 95%, Rest ≥ 70%.

---

## 14. Erster Prompt für Claude Code

```
Implementiere Phase 1 dieses Plans (siehe PLAN.md):

Sprach-Regel: Code, Comments, Docstrings, Tests, Schemas alles in Englisch.
Ports-Namen, Methodennamen, Feldnamen alles englisch (siehe Abschnitt 7).

Liefere:
- Projektstruktur unter src/fahrzeugbilder/
- pyproject.toml mit uv, Python 3.12+, ruff, mypy --strict, pytest, hypothesis, python-ulid
- domain/value_objects.py: VehicleId mit registration_number-Validierung (^[A-Za-z0-9._-]{1,64}$)
- domain/entities.py: Vehicle, Repair, Image, ImageSource (gemäss Abschnitt 7)
- domain/exceptions.py: domain-spezifische Exceptions
- domain/ports/ als typing.Protocol:
    VehicleRepository, RepairRepository, ImageRepository,
    StorageBackend, SearchIndex, EmailInbox
- tests/domain/ inkl. property-based für VehicleId-Validierung mit hypothesis
- mypy --strict muss grün sein
- KEIN Framework-Import in domain/ (kein FastAPI, kein SQLAlchemy, kein fsspec)

Akzeptanzkriterium: `uv run pytest && uv run mypy src` läuft ohne Fehler.
```
