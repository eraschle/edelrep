import json
from datetime import UTC, datetime
from pathlib import Path

from edelrep.domain.ports import EmailAttachment, EmailMessage
from edelrep.infrastructure.email.inbox_store import InboxStore
from edelrep.infrastructure.storage import LocalFilesystemBackend


def _msg(
    *,
    subject: str = "Test",
    attachments: tuple[EmailAttachment, ...] = (),
) -> EmailMessage:
    return EmailMessage(
        message_id="<test-msg@example.com>",
        from_address="kunde@firma.ch",
        subject=subject,
        received_at=datetime(2026, 5, 3, 14, 30, 0, tzinfo=UTC),
        body_text="some body",
        attachments=attachments,
    )


def test_park_writes_sidecar_under_system_inbox(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path / "store")
    store = InboxStore(backend)
    msg = _msg()
    slot = store.park(msg)
    assert slot.startswith("_system/inbox/")
    assert "2026-05-03T143000" in slot


def test_park_writes_inbox_json_with_schema_version(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path / "store")
    store = InboxStore(backend)
    msg = _msg()
    slot = store.park(msg)
    raw = backend.read_bytes(f"{slot}/_inbox.json")
    data = json.loads(raw)
    assert data["schema_version"] == 1
    assert data["status"] == "pending"
    assert data["message_id"] == "<test-msg@example.com>"
    assert data["from_address"] == "kunde@firma.ch"
    assert data["subject"] == "Test"
    assert data["received_at"] == "2026-05-03T14:30:00+00:00"


def test_park_writes_attachments_with_index(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path / "store")
    store = InboxStore(backend)
    msg = _msg(
        attachments=(
            EmailAttachment(filename="brake.jpg", mime_type="image/jpeg", content=b"\xff\xd8"),
            EmailAttachment(filename="rotor.png", mime_type="image/png", content=b"\x89PNG"),
        ),
    )
    slot = store.park(msg)
    keys = sorted(backend.list_prefix(f"{slot}/"))
    # Expect: 0001_brake.jpg, 0002_rotor.png, _inbox.json
    names = [k.rsplit("/", 1)[1] for k in keys]
    assert "0001_brake.jpg" in names
    assert "0002_rotor.png" in names
    assert "_inbox.json" in names
    # Bytes preserved.
    assert backend.read_bytes(f"{slot}/0001_brake.jpg") == b"\xff\xd8"


def test_park_with_explicit_status(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path / "store")
    store = InboxStore(backend)
    msg = _msg()
    slot = store.park(msg, status="processed")
    raw = backend.read_bytes(f"{slot}/_inbox.json")
    data = json.loads(raw)
    assert data["status"] == "processed"


def test_park_handles_filename_with_slash(tmp_path: Path) -> None:
    """Slashes in filenames must be sanitized to avoid escaping the slot."""
    backend = LocalFilesystemBackend(tmp_path / "store")
    store = InboxStore(backend)
    msg = _msg(
        attachments=(
            EmailAttachment(filename="path/with/slash.jpg", mime_type="image/jpeg", content=b"x"),
        ),
    )
    slot = store.park(msg)
    keys = list(backend.list_prefix(f"{slot}/"))
    names = [k.rsplit("/", 1)[1] for k in keys]
    assert any(name.startswith("0001_") and "/" not in name for name in names)


def test_park_handles_empty_filename(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path / "store")
    store = InboxStore(backend)
    msg = _msg(
        attachments=(
            EmailAttachment(filename="", mime_type="application/octet-stream", content=b"x"),
        ),
    )
    slot = store.park(msg)
    keys = list(backend.list_prefix(f"{slot}/"))
    names = [k.rsplit("/", 1)[1] for k in keys]
    assert any(name.startswith("0001_") for name in names)


def test_park_returns_unique_slots_for_same_received_at(tmp_path: Path) -> None:
    """Two messages received at the exact same time get different slots due to ULID."""
    backend = LocalFilesystemBackend(tmp_path / "store")
    store = InboxStore(backend)
    msg1 = _msg()
    msg2 = _msg()
    slot1 = store.park(msg1)
    slot2 = store.park(msg2)
    assert slot1 != slot2
