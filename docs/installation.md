# Installation

Anleitung zur Einrichtung von edelrep für **Entwicklung** und **Produktion**. Für Deployment-spezifische Themen (systemd, Docker) siehe [`../deploy/README.md`](../deploy/README.md).

## Systemanforderungen

| Komponente | Mindestanforderung |
|---|---|
| Python | 3.13 oder neuer |
| `uv` | aktuelle Version (Astral-Tool für Python-Pakete) |
| Speicher | ~150 MB für die App + Abhängigkeiten; Storage-Bedarf hängt von der Bildmenge ab |
| Betriebssystem | Linux, macOS, Windows. Code ist OS-unabhängig (`pathlib` + plattformneutrale Bibliotheken) |

`uv` kann Python 3.13 bei Bedarf selbst herunterladen — eine systemweite Python-3.13-Installation ist daher nicht zwingend nötig.

## Entwicklungs-Setup

### 1. uv installieren

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Alternativ: über pip
pip install uv
```

### 2. Repository klonen

```bash
git clone <repo-url> edelrep
cd edelrep
```

> Falls du `edelrep` nur lokal entwickelst und kein Remote-Repository hinterlegt ist, ersetze den `git clone`-Schritt durch einen Pfad zum lokalen Workspace.

### 3. Abhängigkeiten installieren

```bash
uv sync
```

`uv sync` legt ein virtuelles Env unter `.venv/` an, installiert alle Runtime- und Dev-Abhängigkeiten aus `pyproject.toml` / `uv.lock`. Wenn du Python 3.13 noch nicht installiert hast, lädt `uv` es automatisch herunter.

### 4. Tests laufen lassen (optional, zur Verifikation)

```bash
uv run pytest
```

Erwartet: 499 Tests grün, ~3-5 Sekunden Laufzeit.

### 5. Web-Server starten

```bash
uv run edelrep serve \
  --storage-root ./storage \
  --index-path ./index.db
```

Browser: <http://127.0.0.1:8080>.

Beim ersten Start werden `./storage` und das Verzeichnis von `./index.db` automatisch angelegt.

## Produktions-Installation (Linux)

Für ein dediziertes Deployment auf einem Mini-PC / Server.

### 1. Pakete

```bash
sudo apt update
sudo apt install python3.13 python3.13-venv git
```

(Falls Python 3.13 in der Paketquelle fehlt, gibt es passende PPAs oder `pyenv`. Alternativ kann `uv` die Python-Version selbst verwalten.)

### 2. Anwendung installieren

```bash
sudo pip install uv
sudo useradd --system --home /var/lib/edelrep --create-home edelrep
sudo mkdir -p /opt/edelrep
sudo chown edelrep:edelrep /opt/edelrep
sudo -u edelrep git clone <repo-url> /opt/edelrep/app
cd /opt/edelrep/app
sudo -u edelrep uv sync --no-dev
```

### 3. Verzeichnisse vorbereiten

```bash
sudo mkdir -p /var/lib/edelrep/data
sudo chown -R edelrep:edelrep /var/lib/edelrep
```

### 4. Systemd-Service

Siehe [`../deploy/README.md`](../deploy/README.md) für die fertige Unit-Datei und Aktivierungsschritte.

### 5. Reverse-Proxy (optional)

Standardmässig bindet `edelrep serve` an `127.0.0.1:8080`. Für TLS / öffentliche Erreichbarkeit empfohlen: nginx oder Caddy davorschalten. edelrep bringt keine eigene TLS-Terminierung mit.

## Docker-Installation

Siehe [`../deploy/README.md`](../deploy/README.md) für `Dockerfile` und `docker-compose.yml`.

Kurzfassung:

```bash
cd deploy
docker compose up -d
```

Volume `./data` wird auf `/data` im Container gemappt — dort liegen `storage` und `index.db`.

## Verifikation

Nach Installation prüfen, dass der CLI-Einstiegspunkt funktioniert:

```bash
uv run edelrep --help
```

Erwartete Ausgabe (Auszug):

```
usage: edelrep [-h] {reindex,watch,serve,migrate-storage} ...

positional arguments:
  {reindex,watch,serve,migrate-storage}
    reindex             Rebuild the SQLite index from filesystem
    watch               Run the live filesystem watcher (Ctrl-C to stop)
    serve               Run the edelrep web UI (Ctrl-C to stop)
    migrate-storage     Copy storage tree to a new location and verify counts
```

Alle 4 Subkommandos müssen sichtbar sein. Wenn nicht: `uv sync` erneut ausführen oder `[project.scripts]` in `pyproject.toml` prüfen.

## Häufige Probleme

| Symptom | Ursache | Lösung |
|---|---|---|
| `ModuleNotFoundError: edelrep` | Editable install fehlt | `uv sync` ausführen |
| `command not found: edelrep` | Script-Eintrag fehlt | `uv run edelrep ...` (statt nacktes `edelrep`) |
| `Python 3.13 required` | Systeme Python zu alt | `uv` installieren — bringt 3.13 mit |
| `sqlite3.OperationalError: no such module: fts5` | SQLite ohne FTS5 (selten unter Linux/macOS) | System-SQLite ≥ 3.9 prüfen; CPython bringt FTS5 i.d.R. eingebaut mit |
| Port 8080 belegt | Anderer Dienst läuft | `--port 8081` oder anderen Wert wählen |

## Nächste Schritte

- [Architecture](architecture.md) — wie ist das System aufgebaut?
- [Configuration](configuration.md) — alle CLI-Optionen und die E-Mail-TOML
- [Development](development.md) — Entwicklungs-Workflow
- [Deployment](../deploy/README.md) — Produktions-Deployment
