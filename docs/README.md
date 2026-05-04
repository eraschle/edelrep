# edelrep — Dokumentation

Diese Verzeichnis enthält die ausführliche Dokumentation. Die Kurzübersicht befindet sich in der [Projekt-README](../README.md).

## Inhalt

| Datei | Thema |
|---|---|
| [installation.md](installation.md) | Schritt-für-Schritt Installation (Linux, macOS, Windows) inkl. Systemanforderungen |
| [architecture.md](architecture.md) | Clean-Architecture-Schichten, Ports & Adapter, Datenfluss, Storage-Layout |
| [configuration.md](configuration.md) | CLI-Referenz, Umgebungsvariablen, E-Mail TOML-Schema |
| [development.md](development.md) | Entwicklungs-Workflow, Test-Strategie, Code-Konventionen |
| [backup.md](backup.md) | Backup & Recovery, Storage-Migration, Cloud-Sync |
| [../deploy/README.md](../deploy/README.md) | Deployment via systemd / Docker |
| [../PLAN.md](../PLAN.md) | Ursprünglicher Phasen-Plan und Architektur-Entscheidungen |
| [superpowers/plans/](superpowers/plans/) | Implementierungs-Pläne pro Phase (1–9) |

## Quickstart

Wenn du nur schnell starten willst: [Quickstart in der README](../README.md#quickstart).

## Architektur in einem Satz

Filesystem ist Source of Truth → Use Cases orchestrieren über Domain-Ports → Adapter (Filesystem, SQLite, IMAP, Pillow, Watchdog) liefern die I/O. Details: [architecture.md](architecture.md).

## Status

V1 ist feature-complete (Phase 1–9). Liste der vorgemerkten v2-Features steht in der [README](../README.md#status-v1).
