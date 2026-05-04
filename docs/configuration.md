# Konfiguration

Vollständige Referenz aller CLI-Optionen, Umgebungsvariablen und der TOML-basierten E-Mail-Konfiguration.

## CLI-Befehle

`edelrep` hat vier Subkommandos. `uv run edelrep --help` für die kanonische Liste.

### `edelrep serve`

Startet die Web-UI (uvicorn) und im Hintergrund den Live-Index sowie optional den E-Mail-Poller.

| Option | Pflicht | Default | Zweck |
|---|---|---|---|
| `--storage-root <path>` | ja | — | Wurzelverzeichnis des Filesystem-Storage |
| `--index-path <path>` | ja | — | Pfad zur SQLite-Index-Datei |
| `--host <host>` | nein | `127.0.0.1` | Bind-Adresse |
| `--port <port>` | nein | `8080` | Bind-Port |
| `--email-config <toml>` | nein | — | TOML-Datei mit IMAP-Konfig (siehe unten) |

Beispiel:

```bash
uv run edelrep serve \
  --storage-root /var/lib/edelrep/data \
  --index-path /var/lib/edelrep/index.db \
  --host 127.0.0.1 \
  --port 8080
```

### `edelrep watch`

Wie `serve`, aber **ohne Web-Server**. Nur der Live-Index läuft. Nützlich, wenn ein anderer Prozess den Web-Server stellt oder zur Diagnose.

| Option | Pflicht | Default | Zweck |
|---|---|---|---|
| `--storage-root <path>` | ja | — | siehe `serve` |
| `--index-path <path>` | ja | — | siehe `serve` |

### `edelrep reindex`

Baut den SQLite-Index von Grund auf neu. Nutze dies nach Restore aus Backup, nach Storage-Migration, oder wenn der Index korrupt ist.

| Option | Pflicht | Default | Zweck |
|---|---|---|---|
| `--storage-root <path>` | ja | — | Filesystem, das gelesen wird |
| `--index-path <path>` | ja | — | SQLite-Datei, die geschrieben wird (existiert oder wird angelegt) |

Bei Schema-Mismatch wird der Index destruktiv neu aufgebaut.

### `edelrep migrate-storage`

Kopiert den Storage-Tree auf einen neuen Pfad mit Verifikation.

| Option | Pflicht | Default | Zweck |
|---|---|---|---|
| `--from <path>` | ja | — | Quelle (muss existieren) |
| `--to <path>` | ja | — | Ziel (muss leer / nicht-existent sein) |

Verwendet `shutil.copytree` (lokaler Pfad-zu-Pfad-Kopier). Vergleicht nach dem Kopieren die Dateianzahl. Bricht bei Diskrepanz ab.

## Umgebungsvariablen

edelrep selbst liest keine Umgebungsvariablen direkt. Indirekt:

- **`EMAIL_PASSWORD`** (oder ein anderer Name nach `password_env` in der TOML) wird zur Laufzeit ausgelesen, wenn `--email-config` gesetzt ist und die IMAP-Anmeldung erfolgt.
- Weitere Variablen aus den verwendeten Bibliotheken (uvicorn `UVICORN_*`, watchdog OS-spezifisch) sind selten relevant.

## E-Mail-Konfiguration (`--email-config`)

Wenn die `serve`-CLI mit `--email-config /pfad/zur/email.toml` gestartet wird, wird der IMAP-Poller aktiviert.

### TOML-Schema

```toml
[email]
enabled = true                                    # bool, default true
host = "imap.firma.ch"                            # string, Pflicht
user = "werkstatt@firma.ch"                       # string, Pflicht
password_env = "EMAIL_PASSWORD"                   # string, Pflicht (Name einer Env-Variable)
folder = "INBOX"                                  # string, default "INBOX"
poll_interval_seconds = 300                       # int, default 300
max_attachment_mb = 25                            # int, default 25
allowed_senders = ["*@firma.ch", "kunde@x.ch"]    # list[str], default []
```

| Feld | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| `enabled` | bool | nein | Wenn `false`, wird der Poller nicht gestartet (auch wenn `--email-config` übergeben). |
| `host` | string | **ja** | IMAP-Host (z.B. `imap.gmail.com`, `imap.firma.ch`). |
| `user` | string | **ja** | IMAP-Login-Benutzername. |
| `password_env` | string | **ja** | **Name** einer Umgebungsvariable, aus der das Passwort gelesen wird. Niemals das Passwort direkt in der TOML speichern. |
| `folder` | string | nein | Mailbox-Ordner (Default `INBOX`). |
| `poll_interval_seconds` | int | nein | Polling-Intervall (Default 300 = 5 min). |
| `max_attachment_mb` | int | nein | Maximalgrösse pro Attachment in MiB. Grössere Attachments werden gefiltert. |
| `allowed_senders` | list[str] | nein | (V1: noch nicht erzwungen — vorbereitet für spätere Phase) |

### Stammnummer-Erkennung

Der `EmailSubjectParser` versucht in dieser Reihenfolge:

1. **Subject**: regex `Stamm(nummer|nr|n)?[\s:]+<id>` oder `#<id>`
2. **Body, erste Zeile**: gleiche Patterns
3. **Anhang-Filename**: führende Ziffern (`12345_brake.jpg` → `12345`)

Findet sich keine Stammnummer (oder die Nummer ist als `VehicleId` ungültig oder das Fahrzeug existiert nicht), landet die E-Mail im Posteingang unter `<storage_root>/_system/inbox/<received_iso>_<ulid>/`. Der Posteingang ist über die UI sichtbar (`/inbox`).

### Beispiel: Komplettes Setup

Datei `/etc/edelrep/email.toml`:

```toml
[email]
enabled = true
host = "imap.firma.ch"
user = "werkstatt@firma.ch"
password_env = "EMAIL_PASSWORD"
folder = "edelrep-inbox"
poll_interval_seconds = 180
max_attachment_mb = 30
```

Start (lokal):

```bash
EMAIL_PASSWORD="<password>" uv run edelrep serve \
  --storage-root ./storage \
  --index-path ./index.db \
  --email-config /etc/edelrep/email.toml
```

Start (systemd) — siehe [`../deploy/README.md`](../deploy/README.md) für die Variante mit `EnvironmentFile=`.

## Storage-Layout-Konfiguration

Der `--storage-root` kann auf jedes Verzeichnis zeigen, das edelrep schreiben darf. Empfehlungen:

- **Entwicklung**: `./storage` im Projekt-Root.
- **Linux-Server**: `/var/lib/edelrep/data`.
- **macOS**: `~/Library/Application Support/edelrep/data` oder `/usr/local/var/edelrep/data`.
- **Windows**: `%LOCALAPPDATA%\edelrep\data` oder `C:\edelrep\data`.
- **Cloud-Sync**: ein Ordner unter Nextcloud/Dropbox/OneDrive (z.B. `~/Nextcloud/edelrep/`). Der Sync-Client repliziert dann automatisch.

Der `--index-path` kann irgendwo liegen — er wird nicht ins Backup eingeschlossen und ist jederzeit aus dem Storage rekonstruierbar.

## Empfohlene Verzeichnisrechte

Wenn edelrep als unprivilegierter `edelrep`-User läuft:

```bash
sudo install -d -o edelrep -g edelrep -m 0750 /var/lib/edelrep
sudo install -d -o edelrep -g edelrep -m 0750 /var/lib/edelrep/data
sudo install -d -o edelrep -g edelrep -m 0750 /etc/edelrep
sudo install -m 0640 -o root -g edelrep email.toml /etc/edelrep/email.toml
```

`/etc/edelrep/email.toml` muss vom edelrep-User lesbar sein, das Passwort kommt aber aus der Env-Variable.

## Limits & Annahmen (V1)

- **Single-Tenant**: ein Workshop, ein Storage-Root.
- **Single-Process**: kein Locking zwischen mehreren `edelrep serve`-Instanzen auf demselben Storage. Wenn nötig: Reverse-Proxy + ein Backend.
- **Grösse**: getestet bis ~1000 Fahrzeuge, ~10 Reparaturen/Fahrzeug, ~5 Bilder/Reparatur. FTS5-Suche bleibt < 50 ms.
- **Bild-Maximalgrösse**: nicht hart limitiert in der CLI — der E-Mail-Poller respektiert `max_attachment_mb`.

## Weiterführend

- [Installation](installation.md)
- [Architecture](architecture.md)
- [Backup](backup.md)
- [Deployment](../deploy/README.md)
