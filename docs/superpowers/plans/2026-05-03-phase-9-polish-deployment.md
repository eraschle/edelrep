# Phase 9 — Polish & Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the V1 deployment story. Add Posteingang UI (deferred from Phase 8). Add storage migration CLI. Provide systemd + Docker deployment artefacts. Write production README + backup documentation. Close lingering coverage gaps. Tag `phase-9-complete`.

**Definition of Done (PLAN.md §12 Phase 9):**
- "Frischer Mini-PC bootet die App in < 5 Min Setup" — verified by following the README on a clean environment.
- Posteingang `GET /inbox` lists parked messages from `_system/inbox/`.
- `edelrep migrate-storage --from <p> --to <p>` copies the storage tree and verifies counts.
- `deploy/edelrep.service` (systemd) and `deploy/Dockerfile` + `deploy/docker-compose.yml` checked in.
- `docs/backup.md` explains backup procedure.
- `README.md` is production-grade with quickstart, config, deployment.
- Pyright/pytest/ruff green; coverage ≥ 95%; all source files (excluding deploy/templates) ≥ 90%.
- Tag `phase-9-complete`.

**Branch:** `phase-9-polish-deployment` (off `master` at `9159156`).

---

## File Structure

**Created:**

```
src/edelrep/infrastructure/email/
└── inbox_reader.py                     # InboxReader (lists parked messages)

src/edelrep/application/
└── migrate_storage.py                  # MigrateStorageUseCase

src/edelrep/presentation/
├── routes/
│   └── inbox.py                        # GET /inbox, GET /inbox/<slot>
└── templates/
    ├── inbox.html
    └── inbox_detail.html

deploy/
├── edelrep.service                     # systemd unit
├── Dockerfile
├── docker-compose.yml
└── README.md                           # deployment notes

docs/
└── backup.md

tests/infrastructure/email/
└── test_inbox_reader.py

tests/application/
└── test_migrate_storage.py

tests/presentation/
└── test_inbox.py
```

**Modified:**

```
README.md                                # production rewrite
src/edelrep/cli/main.py                  # add migrate-storage subcommand
src/edelrep/presentation/app_factory.py  # include inbox router
```

**Deferred coverage closures targeted at:**
- `src/edelrep/infrastructure/email/imap_adapter.py` lines 48-49
- `src/edelrep/application/ingest_email.py` lines 85-87, 120
- `src/edelrep/presentation/routes/repairs.py` lines 46-47

---

## Design Notes

### InboxReader

Pure read-only. Implements:

```python
@dataclass(frozen=True, slots=True)
class ParkedMessage:
    slot_id: str          # e.g. "_system/inbox/2026-05-03T143000_01J9..."
    message_id: str
    from_address: str
    subject: str
    received_at: datetime
    status: str
    attachment_keys: tuple[str, ...]   # full storage keys


class InboxReader:
    def __init__(self, backend: StorageBackend) -> None: ...

    def list_pending(self) -> list[ParkedMessage]:
        """Walk `_system/inbox/<slot>/_inbox.json` files; return all parked messages."""

    def get(self, slot_id: str) -> ParkedMessage:
        """Return one parked message; raises FileNotFoundError if missing."""
```

Uses `backend.list_prefix("_system/inbox/")` + sidecar filtering. Sorted newest-first by `received_at`.

### Posteingang routes

```python
GET /inbox        -> list page with all parked messages
GET /inbox/<slot> -> detail page with attachment thumbnails (served via existing /images/* equivalent)
```

`<slot>` is URL-encoded slot identifier (just the basename, e.g. `2026-05-03T143000_01J9...`). The detail page serves attachments via `GET /inbox/<slot>/attachments/<filename>` for inline preview.

### MigrateStorageUseCase

Application-layer wrapper around `shutil.copytree`. Local-only for V1.

```python
@dataclass(frozen=True, slots=True)
class MigrationStats:
    files_copied: int
    bytes_copied: int
    duration_seconds: float


class MigrateStorageUseCase:
    def execute(
        self, *, source_root: Path, target_root: Path,
    ) -> MigrationStats: ...
```

Steps:
1. Refuse if `target_root` exists and is non-empty (safety).
2. `shutil.copytree(source_root, target_root, dirs_exist_ok=False)`.
3. Verify by listing files in both — counts must match.
4. Return stats.

### CLI

`edelrep migrate-storage --from <path> --to <path>`. Composition root just instantiates the use case (no LiveIndex / SQL needed). Prints stats. Exit 0 on success.

### Deploy artefacts

`deploy/edelrep.service`:

```ini
[Unit]
Description=edelrep — Fahrzeug-Reparatur-Verwaltung
After=network.target

[Service]
Type=simple
User=edelrep
WorkingDirectory=/var/lib/edelrep
ExecStart=/usr/local/bin/edelrep serve \
  --storage-root /var/lib/edelrep/data \
  --index-path /var/lib/edelrep/index.db \
  --host 127.0.0.1 \
  --port 8080
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`deploy/Dockerfile`:

```dockerfile
FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8080
CMD ["edelrep", "serve", \
     "--storage-root", "/data/storage", \
     "--index-path", "/data/index.db", \
     "--host", "0.0.0.0", \
     "--port", "8080"]
```

`deploy/docker-compose.yml`:

```yaml
services:
  edelrep:
    build: ..
    image: edelrep:latest
    ports:
      - "127.0.0.1:8080:8080"
    volumes:
      - ./data:/data
    restart: unless-stopped
```

`deploy/README.md`: short pointers to systemd vs docker setup.

### docs/backup.md

Concise. Covers: storage_root is the truth, SQLite is rebuildable, recommended `rsync` cron, restore steps, cloud-sync via Nextcloud points to storage_root.

### README.md (production)

Sections (German + English mix):
1. **edelrep** — one-liner: "Lokal betriebene Web-App für Fahrzeugbild- und Reparatur-Verwaltung".
2. **Quickstart** — `uv tool install edelrep`-style or pip + `edelrep serve --storage-root ./storage --index-path ./index.db`.
3. **Architecture** — pointer to PLAN.md.
4. **Configuration** — TOML for email.
5. **Deployment** — systemd + docker pointers.
6. **Backup & Recovery** — pointer to docs/backup.md.
7. **CLI** — list of commands.
8. **Status** — V1 deferred items (auth, multi-tenant).
9. **License / Contributing** — placeholder.

---

## Task 1: InboxReader (TDD)

Create reader; tests verify listing, sorting newest-first, sidecar parsing, slot key extraction. Implementation walks `backend.list_prefix("_system/inbox/")` filtered to `_inbox.json` keys.

Commit: `feat(email): add InboxReader for listing parked messages`.

---

## Task 2: Posteingang routes + templates (TDD)

Routes:
- `GET /inbox` → list page
- `GET /inbox/{slot}` → detail page
- `GET /inbox/{slot}/attachments/{filename}` → serve attachment bytes

Templates: `inbox.html` (list with date + sender + subject + count), `inbox_detail.html` (attachments thumbnails).

Tests use TestClient; seed `InboxStore.park()` then GET routes, assert content.

Commit: `feat(presentation): add Posteingang routes and templates`.

---

## Task 3: MigrateStorageUseCase + CLI (TDD)

Use case + tests against `tmp_path`. CLI subcommand `migrate-storage` calls it.

Commit: `feat(application): add MigrateStorageUseCase and CLI command`.

---

## Task 4: Coverage gap closures

Targeted tests for:
- `imap_adapter.py` 48-49 (the `try/except (ValueError, TypeError)` on `raw.date.astimezone(UTC)`)
- `ingest_email.py` 85-87 (DuplicateRepair fallback path) and 120 (no-image branch already covered? verify)
- `repairs.py` 46-47 (the `InvalidVehicleId` except in POST)

Each one is a small targeted test.

Commit: `test: close coverage gaps in email adapter, ingest use case, repair routes`.

---

## Task 5: docs/backup.md

Write the backup documentation. ~50-100 lines of Markdown.

Commit: `docs: add backup documentation`.

---

## Task 6: deploy/ artefacts

`deploy/edelrep.service`, `deploy/Dockerfile`, `deploy/docker-compose.yml`, `deploy/README.md` per design notes above.

Verification: `systemd-analyze verify deploy/edelrep.service` if available (skip otherwise — the unit file is plain INI).

Commit: `feat(deploy): add systemd unit, Dockerfile, and docker-compose for deployment`.

---

## Task 7: Production README

Rewrite `README.md` per design notes. Replace the current minimal README.

Commit: `docs: production-grade README with quickstart, config, deployment`.

---

## Task 8: Phase 9 acceptance + tag

- All gates green.
- Coverage ≥ 95% overall, ≥ 90% per file.
- Domain + application + OS-independence guards clean.
- E2E: `uv run edelrep serve --help` shows all subcommands (serve, watch, reindex, migrate-storage).
- Tag `phase-9-complete`.

---

## Self-Review Notes

- **Spec coverage (PLAN.md §12 Phase 9):** Storage migration ✅; systemd unit + Docker ✅; backup doc ✅; production README ✅; Posteingang UI ✅ (carried over from Phase 7/8).
- **Out of scope:** Manual inbox assignment (POST /inbox/<slot>/assign moving attachments to a vehicle) — defer to v2; UI list+view is sufficient for V1.
- **DoD verification:** the "<5 Min Setup" claim is qualitative — running through the README on a clean Ubuntu container is the proof. Document that step in README's quickstart.
- **Open follow-ups (post-V1):** auth/login (fastapi-users), backup automation (rclone schedule), audit-log (sidecar history), per-image sidecar with EXIF/source persistence, multi-language (FR/IT) UI.
