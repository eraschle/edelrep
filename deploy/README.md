# Deployment

Zwei unterstützte Wege, edelrep auf einem Server zu betreiben.

## Option 1 — systemd (Linux Server)

```bash
# 1. Pakete installieren
sudo apt install python3.13 python3.13-venv

# 2. edelrep installieren
sudo pip install uv
sudo uv tool install edelrep   # oder via lokalem Wheel

# 3. System-User anlegen
sudo useradd --system --home /var/lib/edelrep --create-home edelrep

# 4. systemd-Unit kopieren und aktivieren
sudo cp deploy/edelrep.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now edelrep

# 5. Status prüfen
sudo systemctl status edelrep
curl http://127.0.0.1:8080/search
```

Reverse-Proxy für TLS / öffentliche Domain (z.B. nginx) separat einrichten.

## Option 2 — Docker Compose

```bash
cd deploy
docker compose up -d
docker compose logs -f
```

Volumes: `./data` enthält den `storage_root` und den SQLite-Index. Backup: nur `data/` mitsichern; `data/index.db` ist wegwerfbar (`edelrep reindex` regeneriert ihn).

## Option 3 — Windows (Werkstatt-Autostart)

[`start_edelrep.bat`](start_edelrep.bat) startet edelrep im LAN-Modus; Logs landen in `edelrep.log`. Batch beim Anmelden ausführen lassen (z.B. Verknüpfung im Autostart-Ordner `shell:startup`).

Zwei Windows-spezifische Stolpersteine, die das Batch bereits berücksichtigt:

- **`.venv`-Erstellung schlägt fehl mit „linking across drives".** `uv` verlinkt Pakete per Hardlink aus seinem Cache; Hardlinks funktionieren unter Windows nicht laufwerksübergreifend. Liegt der Cache auf `C:` und das Projekt auf `D:`, `set UV_LINK_MODE=copy` setzen (macht das Batch). Alternativ den Cache aufs Projekt-Laufwerk legen: `set UV_CACHE_DIR=D:\uv-cache`.
- **Start schlägt fehl mit „Anwendungssteuerungsrichtlinie hat diese Datei blockiert" (os error 4551).** Eine Richtlinie (Smart App Control / WDAC / AppLocker) blockiert den unsignierten `edelrep.exe`-Shim. Deshalb startet das Batch über den Interpreter: `uv run python -m edelrep.cli.main serve …` statt `uv run edelrep serve …`. Ein Neuerstellen der `.venv` hilft hier nicht — der Shim wird identisch neu erzeugt und nach derselben Regel wieder blockiert.

Der Index unter `--index-path` ist wegwerfbar: fehlt er (frische Installation, gelöscht, Upgrade), baut der Server ihn beim Start automatisch aus dem `--storage-root` neu auf.

## E-Mail-Konfiguration (optional)

Wenn der IMAP-Poller laufen soll, eine TOML-Datei z.B. unter `/etc/edelrep/email.toml`:

```toml
[email]
enabled = true
host = "imap.firma.ch"
user = "werkstatt@firma.ch"
password_env = "EMAIL_PASSWORD"
folder = "INBOX"
poll_interval_seconds = 300
max_attachment_mb = 25
```

`EMAIL_PASSWORD` wird zur Laufzeit aus dem Environment gelesen — nie im Klartext in die TOML-Datei schreiben.

systemd: `EnvironmentFile=/etc/edelrep/email.env` mit `EMAIL_PASSWORD=...`. Docker: `environment:` Block in `docker-compose.yml`.

## Backup

Siehe [`../docs/backup.md`](../docs/backup.md).
