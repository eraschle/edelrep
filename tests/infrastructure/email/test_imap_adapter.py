from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from edelrep.domain.ports import EmailMessage
from edelrep.infrastructure.email.imap_adapter import ImapInbox


def _mock_mailmessage(
    *,
    msg_id: str = "<test@x>",
    from_: str = "kunde@firma.ch",
    subject: str = "Stammnr 12345",
    date: datetime | None = None,
    text: str = "body",
) -> MagicMock:
    msg = MagicMock()
    msg.uid = "100"
    msg.from_ = from_
    msg.subject = subject
    msg.date = date or datetime(2026, 5, 3, 14, 30, tzinfo=UTC)
    msg.text = text
    msg.headers = {"message-id": (msg_id,)}
    msg.attachments = []
    return msg


def _mock_mailbox_context(messages: list[MagicMock]) -> tuple[MagicMock, MagicMock]:
    """Build a MailBox mock whose login() acts as context manager returning the box.

    The real imap-tools API: MailBox(host).login(user, pwd, initial_folder=folder)
    returns *self* (the MailBox), which is then used as a context manager.
    So MockMailBox.return_value.login.return_value must be the box itself, and
    that box must support __enter__ / __exit__.
    """
    box = MagicMock()
    box.fetch.return_value = iter(messages)
    box.uids.return_value = ["100"]
    box.flag.return_value = None

    # Make the box itself act as a context manager returning itself
    box.__enter__ = MagicMock(return_value=box)
    box.__exit__ = MagicMock(return_value=False)

    # login() returns the box (which is the context manager)
    box.login.return_value = box

    return box, box


def test_init_stores_config() -> None:
    inbox = ImapInbox(host="imap.example.com", user="u", password="p", folder="INBOX")
    assert inbox._host == "imap.example.com"  # type: ignore[attr-defined]


def test_fetch_unread_returns_email_messages() -> None:
    msg = _mock_mailmessage(msg_id="<m1@x>", subject="Stammnr 99999")
    box, _ = _mock_mailbox_context([msg])
    with patch("edelrep.infrastructure.email.imap_adapter.MailBox") as mock_mailbox:
        mock_mailbox.return_value = box
        inbox = ImapInbox(host="h", user="u", password="p")
        results = inbox.fetch_unread(limit=10)
    assert len(results) == 1
    assert isinstance(results[0], EmailMessage)
    assert results[0].subject == "Stammnr 99999"
    assert results[0].from_address == "kunde@firma.ch"


def test_fetch_unread_respects_limit() -> None:
    msgs = [_mock_mailmessage(msg_id=f"<m{i}@x>") for i in range(5)]
    box, _ = _mock_mailbox_context(msgs)
    with patch("edelrep.infrastructure.email.imap_adapter.MailBox") as mock_mailbox:
        mock_mailbox.return_value = box
        inbox = ImapInbox(host="h", user="u", password="p")
        results = inbox.fetch_unread(limit=3)
    # The adapter requested limit=3; the iter is bounded by our internal counter.
    assert len(results) <= 3


def test_fetch_unread_converts_attachments() -> None:
    msg = _mock_mailmessage()
    att = MagicMock()
    att.filename = "brake.jpg"
    att.content_type = "image/jpeg"
    att.payload = b"\xff\xd8"
    msg.attachments = [att]
    box, _ = _mock_mailbox_context([msg])
    with patch("edelrep.infrastructure.email.imap_adapter.MailBox") as mock_mailbox:
        mock_mailbox.return_value = box
        inbox = ImapInbox(host="h", user="u", password="p")
        results = inbox.fetch_unread(limit=10)
    assert len(results[0].attachments) == 1
    assert results[0].attachments[0].filename == "brake.jpg"
    assert results[0].attachments[0].mime_type == "image/jpeg"
    assert results[0].attachments[0].content == b"\xff\xd8"


def test_fetch_unread_handles_missing_date() -> None:
    msg = _mock_mailmessage()
    msg.date = None
    box, _ = _mock_mailbox_context([msg])
    with patch("edelrep.infrastructure.email.imap_adapter.MailBox") as mock_mailbox:
        mock_mailbox.return_value = box
        inbox = ImapInbox(host="h", user="u", password="p")
        results = inbox.fetch_unread(limit=10)
    # Should not crash; falls back to current UTC.
    assert results[0].received_at.tzinfo is not None


def test_mark_processed_sets_seen_flag() -> None:
    box, _ = _mock_mailbox_context([])
    with patch("edelrep.infrastructure.email.imap_adapter.MailBox") as mock_mailbox:
        mock_mailbox.return_value = box
        inbox = ImapInbox(host="h", user="u", password="p")
        inbox.mark_processed("<m1@x>")
    box.flag.assert_called_once()
    args = box.flag.call_args
    assert args.args[1] == "\\Seen" or args.kwargs.get("flag_set") == "\\Seen"
    assert args.args[2] is True or args.kwargs.get("value") is True


def test_mark_processed_handles_missing_message_gracefully() -> None:
    box, _ = _mock_mailbox_context([])
    box.uids.return_value = []  # message not found
    with patch("edelrep.infrastructure.email.imap_adapter.MailBox") as mock_mailbox:
        mock_mailbox.return_value = box
        inbox = ImapInbox(host="h", user="u", password="p")
        inbox.mark_processed("<unknown@x>")
    # Should not crash; no flag call.
    box.flag.assert_not_called()


def test_fetch_unread_handles_invalid_date_object() -> None:
    """If raw.date.astimezone(UTC) raises (e.g. naive datetime), fall back to now()."""
    msg = _mock_mailmessage()

    class _BadDate:
        def astimezone(self, tz):  # type: ignore[no-untyped-def]
            raise ValueError("naive datetime")

    msg.date = _BadDate()
    box, _ = _mock_mailbox_context([msg])
    with patch("edelrep.infrastructure.email.imap_adapter.MailBox") as mock_mailbox:
        mock_mailbox.return_value = box
        inbox = ImapInbox(host="h", user="u", password="p")
        results = inbox.fetch_unread(limit=10)
    assert results[0].received_at.tzinfo is not None
