# edelrep

Lokal betriebene Web-App zur Verwaltung von Fahrzeugbildern und Reparaturen für Werkstätten. Bilder werden in einer **menschenlesbaren Ordnerstruktur** abgelegt; ein optionaler SQLite-Index sorgt für schnelle Suche. Backup, Cloud-Sync und Storage-Migration funktionieren mit Standard-Werkzeugen (`rsync`, `cp -r`, Nextcloud-Client).

- **Source of Truth**: Filesystem (JSON-Sidecars + Bild-Dateien)
- **Index**: SQLite + FTS5, jederzeit reproduzierbar (`edelrep reindex`)
- **UI**: Server-rendered Jinja2 + HTMX + Tailwind (CDN), deutsche Labels
- **Auth in V1**: keine — nur LAN-Betrieb
- **OS-unabhängig**: Linux, macOS, Windows getestet (CI auf Linux)

Architektur und Phasen-Plan: siehe [`PLAN.md`](PLAN.md).

---

## Quickstart

```bash
# 1. Python 3.13 + uv vorhanden?
python3.13 --version
uv --version

# 2. edelrep installieren
git clone https://github.com/...edelrep.git
cd edelrep
uv sync

# 3. Web-Server starten
uv run edelrep serve \
  --storage-root ./storage \
  --index-path ./index.db
```

Browser: <http://127.0.0.1:8080>.

Klick-Pfad zum Testen:
1. **+ Fahrzeug** → Stammnummer eingeben (z.B. `12345`) → Anlegen
2. **+ Reparatur** auf der Fahrzeug-Detail-Seite → Datum + Beschreibung
3. **Bilder hochladen** → JPEG auswählen
4. **Suche** → Stammnummer eingeben → Treffer anklicken → Reparatur + Bild sichtbar

---

## CLI-Befehle

| Befehl | Zweck |
|---|---|
| `edelrep serve` | Web-Server starten (uvicorn + LiveIndex + optional E-Mail-Poller) |
| `edelrep reindex` | SQLite-Index aus dem Filesystem neu aufbauen |
| `edelrep watch` | Filesystem-Watcher ohne Web-UI laufen lassen |
| `edelrep migrate-storage` | Storage-Tree auf einen neuen Pfad kopieren (mit Verifikation) |

`uv run edelrep --help` für die volle Argument-Liste.

---

## Konfiguration

### Storage- und Index-Pfade

`--storage-root` und `--index-path` als CLI-Argumente. Empfohlene Pfade in Produktion:

```
/var/lib/edelrep/data/      ← storage_root
/var/lib/edelrep/index.db   ← SQLite-Index
```

### E-Mail-Polling (optional)

Eine TOML-Datei mit IMAP-Zugangsdaten anlegen:

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

Eingehende Mails mit `Stamm:`, `Stammnr:`, `#12345` o.ä. im Subject werden automatisch dem Fahrzeug zugeordnet (Bilder werden als neue Reparatur abgelegt). Nicht zuordenbare Mails landen im Posteingang unter `<storage_root>/_system/inbox/`.

---

## Deployment

Siehe [`deploy/README.md`](deploy/README.md) für systemd-Unit und Docker-Compose-Setup.

Kurzfassung — Mini-PC mit Ubuntu in unter 5 Minuten:

```bash
sudo apt install python3.13 python3.13-venv
sudo pip install uv
sudo useradd --system --home /var/lib/edelrep --create-home edelrep
sudo cp deploy/edelrep.service /etc/systemd/system/
sudo systemctl enable --now edelrep
```

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
uv sync                        # Deps installieren
uv run pytest                  # Tests laufen lassen
uv run pyright                 # Type-Check
uv run ruff check .            # Linter
uv run ruff format             # Formatter
```

Test-Coverage liegt bei ~98 %. Phase-Plan-Dokumente: `docs/superpowers/plans/`.

---

## Tech-Stack

- **Python 3.13** (≥ 3.13 erforderlich)
- **FastAPI** + **Jinja2** + **HTMX** + **Tailwind** (CDN) — Web
- **Pillow** — EXIF-Rotation, Thumbnails
- **python-ulid** — sortierbare IDs für Reparaturen und Bilder
- **fsspec** — Storage-Backend-Abstraktion (lokal in V1; S3/WebDAV vorgesehen)
- **SQLite + FTS5** — Such-Index (Wegwerf-Cache)
- **watchdog** — File-System-Events
- **imap-tools** + **APScheduler** — IMAP-Polling
- **uvicorn** — ASGI-Server

---

## Status (V1)

Implementiert (Phase 1–9):

- ✅ Fahrzeug + Reparatur + Bild-Domain
- ✅ Filesystem-Persistence (JSON-Sidecars, atomic write)
- ✅ Storage-Backend-Abstraktion (lokal + fsspec memory:// für Tests)
- ✅ Use-Cases (Upload, List, Search, Get, Reindex, IngestEmail, Migrate)
- ✅ SQLite-Index + FTS5 (1000 Fahrzeuge < 50 ms)
- ✅ Live-Index via watchdog (~2 s Latenz)
- ✅ Web-UI (deutsch, HTMX, Tailwind)
- ✅ E-Mail-Ingestion (auto-route + Posteingang)
- ✅ CLI (`serve`, `reindex`, `watch`, `migrate-storage`)
- ✅ Systemd + Docker Deployment-Artefakte

Vorgemerkt für später (nicht V1):

- 🔜 Auth / Login (LAN-only in V1)
- 🔜 Manuelle Zuordnung im Posteingang (UI listet, aber Zuordnung via CLI/manueller File-Move)
- 🔜 Audit-Log (Sidecar-History)
- 🔜 Mehrsprachigkeit (FR/IT)
- 🔜 fsspec-basierte Storage-Migration (S3, WebDAV)

---

## Lizenz

(noch nicht festgelegt)
