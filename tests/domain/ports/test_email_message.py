from datetime import UTC, datetime

import pytest

from edelrep.domain.ports import EmailMessage


def test_email_message_rejects_naive_received_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        EmailMessage(
            message_id="<id@example.com>",
            from_address="a@b.ch",
            subject="x",
            received_at=datetime(2026, 5, 2, 10, 0),
            body_text="",
            attachments=(),
        )


def test_email_message_accepts_aware_received_at() -> None:
    msg = EmailMessage(
        message_id="<id@example.com>",
        from_address="a@b.ch",
        subject="x",
        received_at=datetime(2026, 5, 2, 10, 0, tzinfo=UTC),
        body_text="",
        attachments=(),
    )
    assert msg.received_at.tzinfo is UTC
