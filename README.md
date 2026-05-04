# edelrep

Lokal betriebene Web-App zur Verwaltung von Fahrzeugbildern und Reparaturen für Werkstätten. Bilder werden in einer **menschenlesbaren Ordnerstruktur** abgelegt; ein optionaler SQLite-Index sorgt für schnelle Suche. Backup, Cloud-Sync und Storage-Migration funktionieren mit Standard-Werkzeugen (`rsync`, `cp -r`, Nextcloud-Client).

- **Source of Truth**: Filesystem (JSON-Sidecars + Bild-Dateien)
- **Index**: SQLite + FTS5, jederzeit reproduzierbar (`edelrep reindex`)
- **UI**: Server-rendered Jinja2 + HTMX + Tailwind (CDN), deutsche Labels
- **Auth in V1**: keine — nur LAN-Betrieb
- **OS-unabhängig**: alle Pfade über `pathlib`, plattformneutrale Bibliotheken (`watchdog`, `apscheduler`, `imap-tools`)

V1 ist feature-complete (Phase 1–9; siehe Tags `phase-1-complete` … `phase-9-complete`). 499 Tests, ~98 % Coverage.

---

## Dokumentation

| Thema | Link |
|---|---|
| Schritt-für-Schritt Installation | [`docs/installation.md`](docs/installation.md) |
| Architektur, Storage-Layout, Datenfluss | [`docs/architecture.md`](docs/architecture.md) |
| CLI-Referenz + E-Mail-TOML | [`docs/configuration.md`](docs/configuration.md) |
| Entwicklungs-Workflow + Test-Strategie | [`docs/development.md`](docs/development.md) |
| Backup & Recovery, Storage-Migration | [`docs/backup.md`](docs/backup.md) |
| Deployment (systemd / Docker) | [`deploy/README.md`](deploy/README.md) |
| Doku-Index | [`docs/README.md`](docs/README.md) |
| Ursprünglicher Phasen-Plan | [`PLAN.md`](PLAN.md) |
| Implementierungs-Pläne pro Phase | [`docs/superpowers/plans/`](docs/superpowers/plans/) |

---

## Quickstart

Voraussetzung: [`uv`](https://docs.astral.sh/uv/) ist installiert. `uv` lädt Python 3.13 bei Bedarf selbst herunter.

```bash
# 1. Repository klonen
git clone <repo-url> edelrep
cd edelrep

# 2. Abhängigkeiten installieren
uv sync

# 3. Web-Server starten
uv run edelrep serve \
  --storage-root ./storage \
  --index-path ./index.db
```

Browser: <http://127.0.0.1:8080>.

Klick-Pfad zum Testen:

1. **+ Fahrzeug** → Stammnummer eingeben (z. B. `12345`) → Anlegen
2. **+ Reparatur** auf der Fahrzeug-Detail-Seite → Datum + Beschreibung
3. **Bilder hochladen** → JPEG auswählen
4. **Suche** → Stammnummer eingeben → Treffer anklicken → Reparatur + Bild sichtbar

Detaillierte Installation und Produktions-Setup: [`docs/installation.md`](docs/installation.md).

---

## CLI-Befehle

| Befehl | Zweck |
|---|---|
| `edelrep serve` | Web-Server starten (uvicorn + LiveIndex + optional E-Mail-Poller) |
| `edelrep reindex` | SQLite-Index aus dem Filesystem neu aufbauen |
| `edelrep watch` | Filesystem-Watcher ohne Web-UI laufen lassen |
| `edelrep migrate-storage` | Storage-Tree auf einen neuen Pfad kopieren (mit Verifikation) |

`uv run edelrep --help` für die volle Argument-Liste. Vollständige Referenz: [`docs/configuration.md`](docs/configuration.md).

---

## Konfiguration

### Storage- und Index-Pfade

`--storage-root` und `--index-path` als CLI-Argumente. Empfohlene Pfade in Produktion:

```
/var/lib/edelrep/data/      ← storage_root
/var/lib/edelrep/index.db   ← SQLite-Index
```

### E-Mail-Polling (optional)

TOML-Datei mit IMAP-Zugangsdaten:

```toml
# /etc/edelrep/email.toml
[email]
enabled = true
host = "imap.firma.ch"
user = "werkstatt@firma.ch"
password_env = "EMAIL_PASSWORD"
folder = "INBOX"
poll_interval_seconds = 300
max_attachment_mb = 25
```

Das Passwort wird zur Laufzeit aus der Umgebungsvariable `EMAIL_PASSWORD` gelesen. Mit aktivierter Konfiguration starten:

```bash
EMAIL_PASSWORD="..." uv run edelrep serve \
  --storage-root ./storage \
  --index-path ./index.db \
  --email-config /etc/edelrep/email.toml
```

Eingehende Mails mit `Stamm:`, `Stammnr:`, `#12345` o.ä. im Subject werden automatisch dem Fahrzeug zugeordnet (Bilder als neue Reparatur). Nicht zuordenbare Mails landen im Posteingang unter `<storage_root>/_system/inbox/` (sichtbar unter `/inbox` im Web-UI).

Vollständiges TOML-Schema: [`docs/configuration.md`](docs/configuration.md).

---

## Deployment

Siehe [`deploy/README.md`](deploy/README.md) für systemd-Unit und Docker-Compose-Setup.

Kurzfassung — Ubuntu-Server in unter 5 Minuten:

```bash
sudo apt install python3.13 python3.13-venv git
sudo pip install uv
sudo useradd --system --home /var/lib/edelrep --create-home edelrep
sudo -u edelrep git clone <repo-url> /opt/edelrep/app
cd /opt/edelrep/app && sudo -u edelrep uv sync --no-dev
sudo cp deploy/edelrep.service /etc/systemd/system/
sudo systemctl enable --now edelrep
```

Reverse-Proxy (TLS) z. B. nginx oder Caddy davorschalten — edelrep bringt keine eigene TLS-Terminierung mit.

---

## Backup

Filesystem ist Source of Truth. Index ist wegwerfbar.

```bash
sudo rsync -a --delete /var/lib/edelrep/data/ /backup/edelrep-data/
```

Wiederherstellung:

```bash
sudo rsync -a /backup/edelrep-data/ /var/lib/edelrep/data/
edelrep reindex --storage-root /var/lib/edelrep/data --index-path /var/lib/edelrep/index.db
```

Details: [`docs/backup.md`](docs/backup.md).

---

## Entwicklung

```bash
uv sync                        # Abhängigkeiten installieren
uv run pytest                  # 499 Tests
uv run pyright                 # Type-Check
uv run ruff check .            # Linter
uv run ruff format             # Formatter
```

Workflow, Konventionen, Architektur-Regeln: [`docs/development.md`](docs/development.md).

---

## Tech-Stack

- **Python 3.13** (≥ 3.13 erforderlich)
- **FastAPI** + **Jinja2** + **HTMX** + **Tailwind** (CDN) — Web
- **Pillow** — EXIF-Rotation, Thumbnails
- **python-ulid** — sortierbare IDs für Reparaturen und Bilder
- **fsspec** — Storage-Backend-Abstraktion (lokal in V1; S3/WebDAV vorgesehen)
- **SQLite + FTS5** — Such-Index (Wegwerf-Cache)
- **watchdog** — File-System-Events (cross-platform: inotify / FSEvents / ReadDirectoryChangesW)
- **imap-tools** + **APScheduler** — IMAP-Polling
- **uvicorn** — ASGI-Server

---

## Status (V1)

Implementiert (Phase 1–9):

- ✅ Fahrzeug + Reparatur + Bild-Domain (frozen+slotted dataclasses, timezone-aware-Invarianten)
- ✅ Filesystem-Persistence (JSON-Sidecars, atomic write, `schema_version=1`)
- ✅ Storage-Backend-Abstraktion (`LocalFilesystemBackend`, `FsspecBackend`)
- ✅ Use-Cases (CreateVehicle, CreateRepair, UploadImage, ListRepairs, GetImage, SearchVehicle, IngestEmail, Reindex, MigrateStorage)
- ✅ SQLite-Index + FTS5 (1000 Fahrzeuge < 50 ms gemessen)
- ✅ Live-Index via watchdog (≤ 10 s SLA cross-platform; ~< 1 s auf Linux/Windows)
- ✅ Web-UI (deutsch, HTMX live-suggestions, Tailwind, Click-Path E2E-Test)
- ✅ E-Mail-Ingestion (IMAP via imap-tools, APScheduler, automatisches Routing nach Stammnummer, Posteingang)
- ✅ CLI (`serve`, `reindex`, `watch`, `migrate-storage`)
- ✅ Deployment-Artefakte (systemd unit, Dockerfile, docker-compose)

Vorgemerkt für später (nicht V1):

- 🔜 Auth / Login (LAN-only in V1)
- 🔜 Manuelle Zuordnung im Posteingang via UI (UI listet, aber Zuordnung aktuell via CLI/manueller File-Move)
- 🔜 Audit-Log via Sidecar-History
- 🔜 Mehrsprachigkeit (FR/IT)
- 🔜 fsspec-basierte Storage-Migration (S3, WebDAV)
- 🔜 Image-Source-Persistierung (aktuell: Reads liefern immer `MANUAL`, da kein per-Image-Sidecar)

---

## Lizenz

(noch nicht festgelegt)
