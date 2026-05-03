from datetime import UTC, datetime
from pathlib import Path

import pytest

from edelrep.domain.ports import EmailAttachment, EmailMessage
from edelrep.infrastructure.email.inbox_reader import InboxReader, ParkedMessage
from edelrep.infrastructure.email.inbox_store import InboxStore
from edelrep.infrastructure.storage import LocalFilesystemBackend


def _msg(
    *,
    msg_id: str = "<m1@x>",
    subject: str = "Test",
    received_at: datetime | None = None,
    attachments: tuple[EmailAttachment, ...] = (),
) -> EmailMessage:
    return EmailMessage(
        message_id=msg_id,
        from_address="kunde@firma.ch",
        subject=subject,
        received_at=received_at or datetime(2026, 5, 3, 14, 30, tzinfo=UTC),
        body_text="",
        attachments=attachments,
    )


def test_list_pending_returns_empty_when_no_inbox(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path / "store")
    reader = InboxReader(backend)
    assert reader.list_pending() == []


def test_list_pending_returns_one_entry_after_park(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path / "store")
    InboxStore(backend).park(_msg())
    reader = InboxReader(backend)
    pending = reader.list_pending()
    assert len(pending) == 1
    assert isinstance(pending[0], ParkedMessage)
    assert pending[0].message_id == "<m1@x>"
    assert pending[0].subject == "Test"
    assert pending[0].status == "pending"


def test_list_pending_sorts_newest_first(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path / "store")
    store = InboxStore(backend)
    store.park(_msg(msg_id="<old@x>", received_at=datetime(2026, 1, 1, tzinfo=UTC)))
    store.park(_msg(msg_id="<new@x>", received_at=datetime(2026, 5, 1, tzinfo=UTC)))
    reader = InboxReader(backend)
    pending = reader.list_pending()
    assert [m.message_id for m in pending] == ["<new@x>", "<old@x>"]


def test_list_pending_includes_attachment_keys(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path / "store")
    store = InboxStore(backend)
    store.park(
        _msg(
            attachments=(
                EmailAttachment(filename="a.jpg", mime_type="image/jpeg", content=b"\xff\xd8"),
                EmailAttachment(filename="b.jpg", mime_type="image/jpeg", content=b"\xff\xd8"),
            ),
        )
    )
    reader = InboxReader(backend)
    pending = reader.list_pending()
    assert len(pending) == 1
    assert len(pending[0].attachment_keys) == 2
    # All keys are inside the slot directory.
    for key in pending[0].attachment_keys:
        assert key.startswith(pending[0].slot_id + "/")


def test_get_returns_specific_parked_message(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path / "store")
    store = InboxStore(backend)
    store.park(_msg(msg_id="<m1@x>"))
    reader = InboxReader(backend)
    pending = reader.list_pending()
    fetched = reader.get(pending[0].slot_id)
    assert fetched.message_id == "<m1@x>"


def test_get_raises_for_unknown_slot(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path / "store")
    reader = InboxReader(backend)
    with pytest.raises(FileNotFoundError):
        reader.get("_system/inbox/nonexistent")


def test_list_pending_skips_directories_without_sidecar(tmp_path: Path) -> None:
    """A slot without _inbox.json is skipped silently."""
    backend = LocalFilesystemBackend(tmp_path / "store")
    InboxStore(backend).park(_msg())
    # Add a stray file under inbox without a sidecar.
    backend.write_bytes("_system/inbox/stray-folder/some-file.txt", b"noise")
    reader = InboxReader(backend)
    pending = reader.list_pending()
    assert len(pending) == 1  # only the properly parked one


def test_get_slot_id_format(tmp_path: Path) -> None:
    """slot_id is the directory portion (under _system/inbox/), no trailing slash."""
    backend = LocalFilesystemBackend(tmp_path / "store")
    InboxStore(backend).park(_msg())
    reader = InboxReader(backend)
    pending = reader.list_pending()
    assert pending[0].slot_id.startswith("_system/inbox/")
    assert not pending[0].slot_id.endswith("/")
