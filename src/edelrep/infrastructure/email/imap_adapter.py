from datetime import UTC, datetime

from imap_tools import AND, MailBox
from imap_tools.query import Header

from edelrep.domain.ports import EmailAttachment, EmailMessage


class ImapInbox:
    """EmailInbox implementation against an IMAP server via imap-tools."""

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        folder: str = "INBOX",
    ) -> None:
        self._host = host
        self._user = user
        self._password = password
        self._folder = folder

    def fetch_unread(self, limit: int = 50) -> list[EmailMessage]:
        out: list[EmailMessage] = []
        with MailBox(self._host).login(  # type: ignore[union-attr]
            self._user, self._password, initial_folder=self._folder
        ) as box:
            for raw in box.fetch(AND(seen=False), limit=limit, mark_seen=False):
                out.append(_to_email_message(raw))
                if len(out) >= limit:
                    break
        return out

    def mark_processed(self, message_id: str) -> None:
        with MailBox(self._host).login(  # type: ignore[union-attr]
            self._user, self._password, initial_folder=self._folder
        ) as box:
            uids = box.uids(AND(header=Header("Message-ID", message_id)))
            if uids:
                box.flag(uids, "\\Seen", True)


def _to_email_message(raw) -> EmailMessage:  # type: ignore[no-untyped-def]
    if raw.date is not None:
        try:
            received_at = raw.date.astimezone(UTC)
        except (ValueError, TypeError):
            received_at = datetime.now(UTC)
    else:
        received_at = datetime.now(UTC)

    headers = getattr(raw, "headers", {}) or {}
    msg_header = headers.get("message-id", ()) if isinstance(headers, dict) else ()
    msg_id = msg_header[0] if msg_header else (raw.uid or "")

    attachments = tuple(
        EmailAttachment(
            filename=a.filename or "unnamed",
            mime_type=a.content_type or "application/octet-stream",
            content=a.payload,
        )
        for a in (raw.attachments or [])
    )
    return EmailMessage(
        message_id=msg_id,
        from_address=raw.from_ or "",
        subject=raw.subject or "",
        received_at=received_at,
        body_text=raw.text or "",
        attachments=attachments,
    )
