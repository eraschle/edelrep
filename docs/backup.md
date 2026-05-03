# Backup & Recovery

## Architektur-Prinzip

Das **Filesystem ist die Source of Truth**:

- Alle Fahrzeug- und Reparaturdaten liegen unter `<storage_root>/` (Voreinstellung: `/var/lib/edelrep/data`).
- Die SQLite-Index-Datenbank (`<index_path>`, Voreinstellung: `/var/lib/edelrep/index.db`) ist **wegwerfbar** — sie kann jederzeit aus dem Filesystem rekonstruiert werden.

Das macht Backups einfach: man sichert nur den `storage_root`. Der Index lässt sich nach einer Wiederherstellung mit einem Befehl neu aufbauen.

## Backup

### Manuell

```bash
sudo rsync -a --delete /var/lib/edelrep/data/ /backup/edelrep-data/
```

### Automatisch (täglich via cron)

`/etc/cron.daily/edelrep-backup`:

```bash
#!/bin/sh
set -e
DEST="/backup/edelrep-$(date +%Y-%m-%d)"
rsync -a --delete /var/lib/edelrep/data/ "$DEST/"
# Optional: aufbewahrte Snapshots auf 30 Tage begrenzen
find /backup -maxdepth 1 -name 'edelrep-*' -mtime +30 -exec rm -rf {} +
```

```bash
sudo chmod +x /etc/cron.daily/edelrep-backup
```

### Cloud-Sync

Statt einer manuellen Backup-Strategie kann der `storage_root` direkt auf einen Cloud-synchronisierten Ordner zeigen:

- **Nextcloud / Dropbox / OneDrive**: Den lokalen Sync-Client auf den `storage_root` zeigen lassen. Die App weiss nichts davon.
- Konflikte zwischen mehreren Werkstatt-Geräten sind in V1 nicht abgesichert — die Annahme ist ein einzelner Server.

## Wiederherstellung

1. Storage-Daten aus dem Backup zurückspielen:

   ```bash
   sudo rsync -a /backup/edelrep-data/ /var/lib/edelrep/data/
   ```

2. SQLite-Index neu aufbauen:

   ```bash
   edelrep reindex \
     --storage-root /var/lib/edelrep/data \
     --index-path /var/lib/edelrep/index.db
   ```

3. App starten — sie liest aus dem rekonstruierten Index, alle Fahrzeuge sind wieder durchsuchbar.

## Storage-Migration (lokaler Pfad-Wechsel)

Wenn der `storage_root` auf eine andere Platte oder einen anderen Pfad verschoben werden soll:

```bash
# 1. App stoppen
sudo systemctl stop edelrep

# 2. Storage kopieren (mit integrierter Verifikation)
edelrep migrate-storage \
  --from /var/lib/edelrep/data \
  --to /mnt/usb-werkstatt/edelrep-data

# 3. systemd-Unit auf neuen Pfad umbiegen, dann starten und reindex
sudo systemctl edit edelrep   # ExecStart anpassen
sudo systemctl start edelrep
edelrep reindex \
  --storage-root /mnt/usb-werkstatt/edelrep-data \
  --index-path /var/lib/edelrep/index.db
```

`edelrep migrate-storage` weigert sich, in ein nicht-leeres Zielverzeichnis zu kopieren, und vergleicht nach dem Kopieren die Dateianzahl von Quelle und Ziel als einfache Verifikation.

## Tipps

- **Niemals** den `index.db` ins Backup einschliessen — er wird nach jeder Wiederherstellung neu gebaut. Eine Inkonsistenz zwischen `storage` und `index` führt sonst zu Fehlern.
- Die `_thumbs/`-Ordner sind aus den Originalbildern reproduzierbar (Phase 4 + reindex). Sie ins Backup einzuschlissen spart Zeit beim Restore.
- Der `_system/inbox/`-Ordner enthält noch nicht zugeordnete E-Mail-Anhänge — bitte mitsichern.

## Troubleshooting

| Symptom | Ursache | Lösung |
|---|---|---|
| Suche findet nichts nach Restore | Index nicht neu gebaut | `edelrep reindex` ausführen |
| `Index ist drifted` Hinweis | Filesystem geändert ohne Watcher | `edelrep reindex` ausführen |
| Anhänge fehlen nach Cloud-Sync | Sync nicht abgeschlossen | Cloud-Client-Logs prüfen |
