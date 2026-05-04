# Phase 8 — E-Mail Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull workshop emails from IMAP, extract Stammnummer from subject/body/attachment-filename, auto-route image attachments to the matching vehicle's repair. Park unrouteable messages in `_system/inbox/<ulid>/`. Background-poll every 5 min via APScheduler. DoD: a test email with an image attachment is processed and the image appears on the vehicle.

**Architecture:** Phase 1's `EmailInbox` Protocol gets a real adapter (`ImapInbox`) wrapping `imap-tools`. New `IngestEmailUseCase` orchestrates parse → route or park. New `InboxStore` writes parked messages to `_system/inbox/<ulid>/`. New `EmailPoller` wraps APScheduler; runs in FastAPI lifespan if configured. CLI `serve` gains an optional `--email-config <toml>` flag.

**Tech Stack:** Python 3.13, `imap-tools>=1.10` (new runtime dep), `apscheduler>=3.11` (new runtime dep), `tomllib` (stdlib for config). All cross-platform.

**Definition of Done:**
- A synthetic `EmailMessage` with a Stammnummer in the subject + JPEG attachment, fed to `IngestEmailUseCase`, results in a new `Repair` on the matching vehicle with the JPEG accessible via the existing image routes.
- Unrouteable messages produce `_system/inbox/<ulid>/_inbox.json` with `status="pending"` plus extracted attachments.
- `EmailPoller` schedules `IngestEmailUseCase.execute()` at the configured interval; clean shutdown.
- `edelrep serve --email-config <toml>` enables the poller; without the flag, email is disabled.
- Pyright/pytest/ruff green; coverage ≥ 95%; new files ≥ 90%.
- OS-independent.
- Tag `phase-8-complete`.

**Out of scope (deferred):**
- Posteingang UI page for manual assignment → Phase 9.
- Real IMAP integration tests (would need an IMAP server). Unit tests use a mocked `imap-tools.MailBox`.
- Outbound email (replies, notifications).
- Per-sender allow-list enforcement at parse time (use simple SQL/dict filter post-fetch if specified).

**Branch:** `phase-8-email-ingestion` (off `master` at `faa820c`).

---

## File Structure

**Created:**

```
src/edelrep/infrastructure/email/
├── __init__.py
├── parser.py                  # EmailSubjectParser (pure regex)
├── inbox_store.py             # InboxStore (writes parked messages)
├── imap_adapter.py            # ImapInbox (implements EmailInbox port)
├── poller.py                  # EmailPoller (APScheduler wrapper)
└── config.py                  # EmailConfig dataclass + load_email_config(toml_path)

src/edelrep/application/
└── ingest_email.py            # IngestEmailUseCase + IngestStats

tests/infrastructure/email/
├── __init__.py
├── test_parser.py
├── test_inbox_store.py
├── test_imap_adapter.py
├── test_poller.py
└── test_config.py

tests/application/
└── test_ingest_email.py
```

**Modified:**

```
pyproject.toml                  # add imap-tools, apscheduler
src/edelrep/cli/main.py         # serve gains --email-config
src/edelrep/presentation/container.py    # build_container takes optional email_config
src/edelrep/presentation/app_factory.py  # lifespan starts/stops EmailPoller
src/edelrep/application/__init__.py      # re-export IngestEmailUseCase
```

---

## Design Notes

### EmailSubjectParser

Pure functions / class. Regex strategies (in order, first match wins):

```python
_PATTERNS = [
    re.compile(r"(?i)stamm(?:nummer|nr|n)?[\s:]*(?P<reg>[A-Za-z0-9._-]+)"),
    re.compile(r"#(?P<reg>[A-Za-z0-9._-]+)"),
]

def parse_subject(subject: str) -> str | None: ...
def parse_body_first_line(body: str) -> str | None: ...
def parse_attachment_filename(filename: str) -> str | None: ...

def extract_registration_number(message: EmailMessage) -> str | None:
    """Try subject, then first body line, then any attachment filename."""
```

Filename leading-digits: `re.match(r"^(\d+)", filename)`.

### InboxStore

Writes parked message under `_system/inbox/<received_iso>_<ulid>/`.

```python
class InboxStore:
    def __init__(self, backend: StorageBackend) -> None: ...
    def park(self, message: EmailMessage, *, status: str = "pending") -> str:
        """Write _inbox.json + extracted attachments. Returns the inbox dir key."""
```

Inbox sidecar (`_inbox.json`) schema:

```json
{
  "schema_version": 1,
  "message_id": "...",
  "from_address": "...",
  "subject": "...",
  "received_at": "2026-05-03T14:30:00+00:00",
  "status": "pending"
}
```

### ImapInbox

```python
class ImapInbox:
    def __init__(self, host: str, user: str, password: str, folder: str = "INBOX") -> None: ...
    def fetch_unread(self, limit: int = 50) -> list[EmailMessage]: ...
    def mark_processed(self, message_id: str) -> None: ...
```

Uses `imap_tools.MailBox(host).login(user, password, initial_folder=folder)`. Iterates `mailbox.fetch(criteria='UNSEEN', limit=limit, mark_seen=False)`. Converts `MailMessage` → `EmailMessage` (our domain DTO). `mark_processed` reconnects, finds the message by `message_id`, sets `\Seen`.

For testing: monkeypatch `imap_tools.MailBox` with a mock object exposing the same surface.

### IngestEmailUseCase

```python
@dataclass(frozen=True, slots=True)
class IngestStats:
    fetched: int
    routed: int
    parked: int
    skipped: int

class IngestEmailUseCase:
    def __init__(
        self,
        inbox: EmailInbox,
        parser: EmailSubjectParser,
        vehicle_repo: VehicleRepository,
        create_repair: CreateRepairUseCase,
        upload_image: UploadImageUseCase,
        inbox_store: InboxStore,
        max_attachment_bytes: int = 25 * 1024 * 1024,
    ) -> None: ...

    def execute(self, *, limit: int = 50) -> IngestStats: ...
```

Per message:
1. Filter image attachments by mime + size.
2. `reg_no = parser.extract_registration_number(message)`.
3. If `reg_no` is None → park (with all attachments) → mark_processed → continue.
4. Try `VehicleId(reg_no)`; if invalid → park.
5. Try `vehicle_repo.exists(vid)`; if False → park.
6. Try `create_repair.execute(vehicle_id=vid, repair_date=received_at.date(), description=subject_truncated)`. On `DuplicateRepair`, find the existing repair for that day+slug and use its id.
7. For each filtered attachment, call `upload_image.execute(repair_id=…, raw_bytes=…, filename=…, source=ImageSource.EMAIL)`.
8. `inbox.mark_processed(message.message_id)`.
9. Return stats.

### EmailPoller

```python
class EmailPoller:
    def __init__(
        self,
        use_case: IngestEmailUseCase,
        interval_seconds: int = 300,
    ) -> None: ...

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def is_running(self) -> bool: ...
```

Wraps `apscheduler.schedulers.background.BackgroundScheduler`. Schedules `use_case.execute()` with `IntervalTrigger(seconds=interval_seconds)`. `start()` is idempotent.

### EmailConfig + TOML loader

```python
@dataclass(frozen=True, slots=True)
class EmailConfig:
    enabled: bool
    host: str
    user: str
    password_env: str
    folder: str = "INBOX"
    poll_interval_seconds: int = 300
    max_attachment_mb: int = 25
    allowed_senders: tuple[str, ...] = ()

def load_email_config(toml_path: Path) -> EmailConfig:
    """Read [email] table from a TOML file."""
```

Password is resolved at use time: `os.environ[config.password_env]`. Never stored in the dataclass.

### Container + app_factory

`build_container(... , email_config: EmailConfig | None = None)`. If provided and `enabled=True`, builds `ImapInbox`, `IngestEmailUseCase`, `EmailPoller`. Container exposes `email_poller: EmailPoller | None`.

`app_factory.create_app` lifespan starts/stops `email_poller` if present.

CLI `serve` gains `--email-config <path>` (optional). When provided, loads config, builds container with email enabled.

---

## Task 1: Add imap-tools + apscheduler deps

**Files:** `pyproject.toml`

Add:
```toml
"apscheduler>=3.11.0",
"imap-tools>=1.10.0",
```

Sync, smoke check imports, gates green.

Commit: `chore(deps): add imap-tools and apscheduler for email ingestion`.

---

## Task 2: Scaffold email subpackage

Markers in `src/edelrep/infrastructure/email/__init__.py` and `tests/infrastructure/email/__init__.py`.

Commit: `feat: scaffold email subpackage`.

---

## Task 3: EmailSubjectParser (TDD)

`tests/infrastructure/email/test_parser.py`:

```python
from datetime import UTC, datetime

from edelrep.domain.ports import EmailMessage
from edelrep.infrastructure.email.parser import (
    EmailSubjectParser,
    extract_registration_number,
    parse_attachment_filename,
    parse_body_first_line,
    parse_subject,
)


def _msg(subject: str = "", body: str = "", attachments: list[str] | None = None) -> EmailMessage:
    from edelrep.domain.ports import EmailAttachment

    atts = [
        EmailAttachment(filename=f, mime_type="image/jpeg", content=b"x")
        for f in (attachments or [])
    ]
    return EmailMessage(
        message_id="<x@x>",
        from_address="a@b.ch",
        subject=subject,
        received_at=datetime(2026, 5, 3, tzinfo=UTC),
        body_text=body,
        attachments=atts,
    )


def test_parse_subject_stammnr_colon() -> None:
    assert parse_subject("Stammnr: 12345") == "12345"


def test_parse_subject_stamm_long_form() -> None:
    assert parse_subject("Stammnummer 12345 Bremsen") == "12345"


def test_parse_subject_hash() -> None:
    assert parse_subject("Bilder #12345 vorne") == "12345"


def test_parse_subject_no_match() -> None:
    assert parse_subject("Hallo, anbei Bilder") is None


def test_parse_body_first_line() -> None:
    assert parse_body_first_line("Stammnr 99999\nBilder anbei") == "99999"


def test_parse_body_no_match_falls_through_lines() -> None:
    # Only the first line is checked.
    assert parse_body_first_line("Hallo\nStammnr 12345") is None


def test_parse_attachment_filename_leading_digits() -> None:
    assert parse_attachment_filename("12345_brakes.jpg") == "12345"


def test_parse_attachment_filename_no_digits() -> None:
    assert parse_attachment_filename("photo.jpg") is None


def test_extract_prefers_subject() -> None:
    msg = _msg(subject="Stammnr 11111", body="Stammnr 22222", attachments=["33333.jpg"])
    assert extract_registration_number(msg) == "11111"


def test_extract_falls_back_to_body() -> None:
    msg = _msg(subject="Hallo", body="Stammnr 22222", attachments=["33333.jpg"])
    assert extract_registration_number(msg) == "22222"


def test_extract_falls_back_to_attachment() -> None:
    msg = _msg(subject="Hallo", body="kein hinweis", attachments=["33333_brakes.jpg"])
    assert extract_registration_number(msg) == "33333"


def test_extract_returns_none_when_nothing_matches() -> None:
    msg = _msg(subject="Hallo", body="kein hinweis", attachments=["photo.jpg"])
    assert extract_registration_number(msg) is None


def test_parser_class_wraps_extract() -> None:
    parser = EmailSubjectParser()
    msg = _msg(subject="Stammnr 12345")
    assert parser.extract_registration_number(msg) == "12345"
```

Implementation `src/edelrep/infrastructure/email/parser.py`:

```python
import re

from edelrep.domain.ports import EmailMessage

_SUBJECT_PATTERNS = [
    re.compile(r"(?i)stamm(?:nummer|nr|n)?[\s:]+(?P<reg>[A-Za-z0-9._-]+)"),
    re.compile(r"#(?P<reg>[A-Za-z0-9][A-Za-z0-9._-]*)"),
]
_BODY_PATTERNS = list(_SUBJECT_PATTERNS)
_FILENAME_LEADING_DIGITS = re.compile(r"^(?P<reg>\d+)")


def parse_subject(subject: str) -> str | None:
    for pattern in _SUBJECT_PATTERNS:
        match = pattern.search(subject)
        if match:
            return match.group("reg")
    return None


def parse_body_first_line(body: str) -> str | None:
    if not body:
        return None
    first_line = body.splitlines()[0]
    for pattern in _BODY_PATTERNS:
        match = pattern.search(first_line)
        if match:
            return match.group("reg")
    return None


def parse_attachment_filename(filename: str) -> str | None:
    match = _FILENAME_LEADING_DIGITS.match(filename)
    return match.group("reg") if match else None


def extract_registration_number(message: EmailMessage) -> str | None:
    if (reg := parse_subject(message.subject)) is not None:
        return reg
    if (reg := parse_body_first_line(message.body_text)) is not None:
        return reg
    for attachment in message.attachments:
        if (reg := parse_attachment_filename(attachment.filename)) is not None:
            return reg
    return None


class EmailSubjectParser:
    """Class wrapper for `extract_registration_number` (DI-friendly)."""

    def extract_registration_number(self, message: EmailMessage) -> str | None:
        return extract_registration_number(message)
```

Commit: `feat(email): add EmailSubjectParser with subject/body/filename strategies`.

---

## Task 4: InboxStore (TDD)

`tests/infrastructure/email/test_inbox_store.py`: test that parking writes the sidecar JSON + numbered attachment files; sidecar has `schema_version=1`, `status="pending"`, ISO datetime; returned dir key is correctly formatted.

Implementation:

```python
import json
from datetime import datetime
from pathlib import Path

from ulid import ULID

from edelrep.domain.ports import EmailMessage, StorageBackend


class InboxStore:
    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend

    def park(self, message: EmailMessage, *, status: str = "pending") -> str:
        slot = self._slot_key(message.received_at)
        sidecar = {
            "schema_version": 1,
            "message_id": message.message_id,
            "from_address": message.from_address,
            "subject": message.subject,
            "received_at": message.received_at.isoformat(),
            "status": status,
        }
        text = json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n"
        self._backend.write_bytes(f"{slot}/_inbox.json", text.encode("utf-8"))
        for i, att in enumerate(message.attachments, start=1):
            safe_name = att.filename.replace("/", "_") if att.filename else f"part{i}.bin"
            self._backend.write_bytes(f"{slot}/{i:04d}_{safe_name}", att.content)
        return slot

    @staticmethod
    def _slot_key(received_at: datetime) -> str:
        ts = received_at.strftime("%Y-%m-%dT%H%M%S")
        return f"_system/inbox/{ts}_{ULID()!s}"
```

Tests use a `LocalFilesystemBackend(tmp_path)`.

Commit: `feat(email): add InboxStore that parks unrouteable messages under _system/inbox/`.

---

## Task 5: IngestEmailUseCase (TDD)

`tests/application/test_ingest_email.py` uses a fake `EmailInbox`, in-memory repos, real `EmailSubjectParser`, real `InboxStore` against `LocalFilesystemBackend(tmp_path)`. Covers:

1. Routed: subject contains Stammnr, vehicle exists → repair created → image uploaded → mark_processed called.
2. Parked because no Stammnr: writes sidecar + attachments to `_system/inbox/...` → mark_processed.
3. Parked because invalid VehicleId: ditto.
4. Parked because vehicle missing: ditto.
5. Image attachment too large: filtered out (no upload, but still routed if parser succeeded — actually if no images remain and reg_no parsed, just mark processed, no upload, no park).
6. Non-image attachments filtered.
7. DuplicateRepair: caught, image goes onto existing repair.

Stats counts: `fetched` (always == messages returned by inbox), `routed` (had reg + vehicle), `parked`, `skipped` (no images at all → mark processed but no work).

Implementation: see `IngestEmailUseCase` design above.

Commit: `feat(application): add IngestEmailUseCase with routing/parking logic`.

---

## Task 6: ImapInbox adapter (TDD with mocked imap-tools)

`tests/infrastructure/email/test_imap_adapter.py` mocks `imap_tools.MailBox` via `unittest.mock.patch`. Verifies:
- Constructor stores config.
- `fetch_unread` calls `MailBox(host).login(user, password, ...)` and returns converted `EmailMessage` instances.
- `mark_processed` reconnects, finds by `message_id`, sets `\Seen`.

Implementation:

```python
from collections.abc import Sequence
from datetime import UTC

from imap_tools import MailBox, MailMessage, AND

from edelrep.domain.ports import EmailAttachment, EmailMessage


class ImapInbox:
    def __init__(self, host: str, user: str, password: str, folder: str = "INBOX") -> None:
        self._host = host
        self._user = user
        self._password = password
        self._folder = folder

    def fetch_unread(self, limit: int = 50) -> list[EmailMessage]:
        out: list[EmailMessage] = []
        with MailBox(self._host).login(self._user, self._password, initial_folder=self._folder) as box:
            count = 0
            for raw in box.fetch(AND(seen=False), limit=limit, mark_seen=False):
                out.append(_to_email_message(raw))
                count += 1
                if count >= limit:
                    break
        return out

    def mark_processed(self, message_id: str) -> None:
        with MailBox(self._host).login(self._user, self._password, initial_folder=self._folder) as box:
            uids = box.uids(AND(header=[("Message-ID", message_id)]))
            if uids:
                box.flag(uids, "\\Seen", True)


def _to_email_message(raw: MailMessage) -> EmailMessage:
    received_at = raw.date.astimezone(UTC) if raw.date else datetime.now(UTC)
    attachments = tuple(
        EmailAttachment(
            filename=a.filename or "unnamed",
            mime_type=a.content_type or "application/octet-stream",
            content=a.payload,
        )
        for a in raw.attachments
    )
    return EmailMessage(
        message_id=raw.uid or raw.headers.get("message-id", ("",))[0] or "",
        from_address=raw.from_ or "",
        subject=raw.subject or "",
        received_at=received_at,
        body_text=raw.text or "",
        attachments=attachments,
    )
```

Note: `imap-tools` API may differ slightly (the implementer should consult the actual library). The test mock validates the contract between `ImapInbox` and the rest of the system, not the imap-tools internals.

Commit: `feat(email): add ImapInbox adapter implementing EmailInbox port`.

---

## Task 7: EmailPoller (TDD)

`tests/infrastructure/email/test_poller.py`:
- `start()` creates and starts the scheduler.
- `start()` is idempotent.
- `stop()` shuts the scheduler down cleanly.
- `is_running()` reflects state.
- The scheduled job calls `use_case.execute()` (test by setting interval=0.1 and waiting briefly, OR by triggering the job manually via the scheduler).

Implementation:

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from edelrep.application.ingest_email import IngestEmailUseCase


class EmailPoller:
    def __init__(self, use_case: IngestEmailUseCase, interval_seconds: int = 300) -> None:
        self._use_case = use_case
        self._interval_seconds = interval_seconds
        self._scheduler: BackgroundScheduler | None = None

    def start(self) -> None:
        if self._scheduler is not None:
            return
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            self._tick,
            trigger=IntervalTrigger(seconds=self._interval_seconds),
            id="edelrep.email.poll",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.start()
        self._scheduler = scheduler

    def stop(self) -> None:
        if self._scheduler is None:
            return
        self._scheduler.shutdown(wait=False)
        self._scheduler = None

    def is_running(self) -> bool:
        return self._scheduler is not None

    def _tick(self) -> None:
        try:
            self._use_case.execute()
        except Exception:  # noqa: BLE001 - poller must not crash on individual run
            import logging
            logging.getLogger(__name__).exception("email poll failed")
```

For testing the timer: use `interval_seconds=0.1`, sleep 0.3s, assert `use_case.execute` was called (use a mock). Alternatively trigger the job manually via `scheduler.get_job(...).func()`.

Commit: `feat(email): add EmailPoller wrapping APScheduler BackgroundScheduler`.

---

## Task 8: EmailConfig + TOML loader (TDD)

`tests/infrastructure/email/test_config.py` writes a TOML file to `tmp_path`, calls `load_email_config(...)`, asserts fields. Cover defaults, missing required fields, type coercion.

Implementation:

```python
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EmailConfig:
    enabled: bool
    host: str
    user: str
    password_env: str
    folder: str = "INBOX"
    poll_interval_seconds: int = 300
    max_attachment_mb: int = 25
    allowed_senders: tuple[str, ...] = field(default_factory=tuple)


def load_email_config(toml_path: Path) -> EmailConfig:
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    section = data.get("email", {})
    required = ["host", "user", "password_env"]
    missing = [k for k in required if k not in section]
    if missing:
        raise ValueError(f"email config missing required keys: {missing}")
    return EmailConfig(
        enabled=bool(section.get("enabled", True)),
        host=str(section["host"]),
        user=str(section["user"]),
        password_env=str(section["password_env"]),
        folder=str(section.get("folder", "INBOX")),
        poll_interval_seconds=int(section.get("poll_interval_seconds", 300)),
        max_attachment_mb=int(section.get("max_attachment_mb", 25)),
        allowed_senders=tuple(section.get("allowed_senders", ())),
    )
```

Commit: `feat(email): add EmailConfig dataclass and TOML loader`.

---

## Task 9: Container + lifespan integration

Modify `presentation/container.py`:
- `build_container` gains `email_config: EmailConfig | None = None`.
- If `email_config and email_config.enabled`: resolve password from `os.environ[email_config.password_env]`, build `ImapInbox`, `IngestEmailUseCase`, `EmailPoller`. Add `email_poller: EmailPoller | None = None` field.

Modify `presentation/app_factory.py` lifespan:

```python
@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    container: Container = app.state.container
    if container.live_index is not None:
        container.live_index.start()
    if container.email_poller is not None:
        container.email_poller.start()
    try:
        yield
    finally:
        if container.email_poller is not None:
            container.email_poller.stop()
        if container.live_index is not None:
            container.live_index.stop()
```

Modify `cli/main.py` `serve` subparser to add `--email-config`. If provided, `_cmd_serve` loads it and passes to `build_container`.

Tests: extend `tests/cli/test_cli.py` with a `--email-config <path>` smoke (composition with a fake/disabled config to avoid real IMAP).

Commit: `feat(presentation): wire EmailPoller into container lifespan and serve CLI`.

---

## Task 10: E2E DoD test

`tests/application/test_ingest_email_e2e.py`:

```python
import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image as PILImage
from ulid import ULID

from edelrep.application.ingest_email import IngestEmailUseCase
from edelrep.domain.ports import EmailAttachment, EmailMessage
from edelrep.infrastructure.email.inbox_store import InboxStore
from edelrep.infrastructure.email.parser import EmailSubjectParser
from edelrep.presentation.container import build_container


class _FakeInbox:
    def __init__(self, messages: list[EmailMessage]) -> None:
        self.messages = list(messages)
        self.processed: list[str] = []

    def fetch_unread(self, limit: int = 50) -> list[EmailMessage]:
        out, self.messages = self.messages[:limit], self.messages[limit:]
        return out

    def mark_processed(self, message_id: str) -> None:
        self.processed.append(message_id)


def _jpeg() -> bytes:
    img = PILImage.new("RGB", (100, 100), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_dod_email_with_attachment_appears_on_vehicle(tmp_path: Path) -> None:
    storage = tmp_path / "store"
    index = tmp_path / "index.db"
    container = build_container(storage, index, with_live_index=False)

    container.create_vehicle.execute(
        registration_number="12345", vin="WDB", description="Kran"
    )

    msg = EmailMessage(
        message_id="<test@example.com>",
        from_address="kunde@firma.ch",
        subject="Stammnr 12345 Bremsen",
        received_at=datetime(2026, 5, 3, 14, 30, tzinfo=UTC),
        body_text="Anbei die Fotos.",
        attachments=(
            EmailAttachment(filename="brake.jpg", mime_type="image/jpeg", content=_jpeg()),
        ),
    )
    inbox = _FakeInbox([msg])
    use_case = IngestEmailUseCase(
        inbox=inbox,
        parser=EmailSubjectParser(),
        vehicle_repo=container.vehicle_repo,
        create_repair=container.create_repair,
        upload_image=container.upload_image,
        inbox_store=InboxStore(container.backend),
    )
    stats = use_case.execute()

    assert stats.fetched == 1
    assert stats.routed == 1
    assert stats.parked == 0
    assert "<test@example.com>" in inbox.processed

    from edelrep.domain.value_objects import VehicleId
    repairs = list(container.list_repairs.execute(VehicleId("12345")))
    assert len(repairs) == 1
    images = list(container.image_repo.list_for_repair(repairs[0].id))
    assert len(images) == 1
    from edelrep.domain.entities import ImageSource
    assert images[0].source == ImageSource.EMAIL  # noqa: B011 - V1 reads default to MANUAL; flag

    container.projector.connection.close()
```

Note: the `source == ImageSource.EMAIL` assertion may fail because `FilesystemImageRepository` reads always return `MANUAL` (Phase 2 limitation: no per-image sidecar). Adjust the assertion to skip that check OR test it via `inbox.processed` and the on-disk presence:

Actually for V1, just verify the image was uploaded (file exists) and a repair was created. The source defaulting to MANUAL on read is a documented Phase 2 limitation. Adjust the test to drop the source assertion.

Commit: `test(application): add E2E DoD test (email with attachment → routed to vehicle)`.

---

## Task 11: Phase 8 acceptance + tag

- Pyright/pytest/ruff green.
- Coverage ≥ 95%; new files ≥ 90%.
- Domain has no `imap_tools|apscheduler` imports.
- Application has no `imap_tools` imports (`apscheduler` may be needed by `IngestEmailUseCase`? No — that's the poller. Application stays clean.)
- OS-independence grep clean.
- E2E smoke: same DoD test, run via pytest.
- Tag `phase-8-complete`.

---

## Self-Review Notes

- **Spec coverage:** ImapInbox ✅; EmailSubjectParser ✅; IngestEmailUseCase ✅; APScheduler ✅; Posteingang UI deferred (PLAN.md specified, but not in DoD; track for Phase 9).
- **Out of scope:** Posteingang UI; outbound email; per-sender allow list (use simple post-fetch dict filter only when configured).
- **Open follow-ups:** Posteingang UI for manual assignment; integration test against a real IMAP test server; per-sender allow list; password rotation (currently: env var lookup at use time).
