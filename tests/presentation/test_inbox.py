import re
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from edelrep.domain.ports import EmailAttachment, EmailMessage
from edelrep.infrastructure.email.inbox_store import InboxStore
from edelrep.presentation.container import Container


def _msg(
    *,
    msg_id: str = "<m1@x>",
    subject: str = "Test E-Mail",
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


def test_inbox_list_renders_when_empty(client: TestClient) -> None:
    response = client.get("/inbox")
    assert response.status_code == 200
    assert "Posteingang" in response.text
    assert "Keine" in response.text or "leer" in response.text.lower()


def test_inbox_list_shows_parked_messages(client: TestClient, container: Container) -> None:
    InboxStore(container.backend).park(_msg(subject="Bremsen vorne"))
    response = client.get("/inbox")
    assert response.status_code == 200
    assert "Bremsen vorne" in response.text
    assert "kunde@firma.ch" in response.text


def test_inbox_list_german_labels(client: TestClient, container: Container) -> None:
    InboxStore(container.backend).park(_msg())
    response = client.get("/inbox")
    text = response.text
    assert "Posteingang" in text
    # Some German label should be present (Absender, Betreff, Eingegangen)
    assert any(label in text for label in ("Absender", "Betreff", "Eingegangen"))


def test_inbox_detail_renders_with_attachments(client: TestClient, container: Container) -> None:
    InboxStore(container.backend).park(
        _msg(
            attachments=(EmailAttachment(filename="brake.jpg", mime_type="image/jpeg", content=b"\xff\xd8"),),
        )
    )
    list_response = client.get("/inbox")
    # Grab the slot link from the rendered HTML.
    match = re.search(r'href="/inbox/([^/"]+)"', list_response.text)
    assert match, "no inbox slot link found in list page"
    slot = match.group(1)

    response = client.get(f"/inbox/{slot}")
    assert response.status_code == 200
    assert "kunde@firma.ch" in response.text
    assert "Test" in response.text  # subject
    # An attachment-preview link should be present.
    assert "/attachments/" in response.text or "brake.jpg" in response.text


def test_inbox_detail_404_for_unknown_slot(client: TestClient) -> None:
    response = client.get("/inbox/nonexistent-slot")
    assert response.status_code == 404


def test_inbox_attachment_serves_bytes(client: TestClient, container: Container) -> None:
    raw = b"\xff\xd8\xff\xd9"
    InboxStore(container.backend).park(
        _msg(
            attachments=(EmailAttachment(filename="brake.jpg", mime_type="image/jpeg", content=raw),),
        )
    )
    list_response = client.get("/inbox")
    match = re.search(r'href="/inbox/([^/"]+)"', list_response.text)
    assert match
    slot = match.group(1)

    detail_response = client.get(f"/inbox/{slot}")
    # Find the attachment href in the detail page.
    att_match = re.search(rf"/inbox/{re.escape(slot)}/attachments/([^\"]+)", detail_response.text)
    assert att_match, "no attachment link found in detail page"
    filename = att_match.group(1)

    response = client.get(f"/inbox/{slot}/attachments/{filename}")
    assert response.status_code == 200
    assert response.content == raw


def test_inbox_attachment_404_for_unknown_filename(client: TestClient, container: Container) -> None:
    InboxStore(container.backend).park(_msg())
    list_response = client.get("/inbox")
    match = re.search(r'href="/inbox/([^/"]+)"', list_response.text)
    assert match
    slot = match.group(1)
    response = client.get(f"/inbox/{slot}/attachments/nonexistent.jpg")
    assert response.status_code == 404
