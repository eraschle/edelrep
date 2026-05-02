from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    filename: str
    mime_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class EmailMessage:
    message_id: str
    from_address: str
    subject: str
    received_at: datetime
    body_text: str
    attachments: Sequence[EmailAttachment]


@runtime_checkable
class EmailInbox(Protocol):
    r"""Inbound port for an external mail server.

    Implementations must be idempotent: marking a message processed twice
    is allowed and silent.
    """

    def fetch_unread(self, limit: int = 50) -> Iterable[EmailMessage]:
        """Return up to ``limit`` unread messages, oldest first."""
        ...

    def mark_processed(self, message_id: str) -> None:
        r"""Flag a message as handled (e.g., set IMAP ``\Seen`` and a label)."""
        ...
