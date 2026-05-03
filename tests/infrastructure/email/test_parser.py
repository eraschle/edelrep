from datetime import UTC, datetime

from edelrep.domain.ports import EmailAttachment, EmailMessage
from edelrep.infrastructure.email.parser import (
    EmailSubjectParser,
    extract_registration_number,
    parse_attachment_filename,
    parse_body_first_line,
    parse_subject,
)


def _msg(
    subject: str = "",
    body: str = "",
    attachments: list[str] | None = None,
) -> EmailMessage:
    atts = tuple(
        EmailAttachment(filename=f, mime_type="image/jpeg", content=b"x")
        for f in (attachments or [])
    )
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


def test_parse_subject_stamm_short() -> None:
    assert parse_subject("Stamm 12345") == "12345"


def test_parse_subject_hash() -> None:
    assert parse_subject("Bilder #12345 vorne") == "12345"


def test_parse_subject_no_match() -> None:
    assert parse_subject("Hallo, anbei Bilder") is None


def test_parse_subject_empty() -> None:
    assert parse_subject("") is None


def test_parse_body_first_line() -> None:
    assert parse_body_first_line("Stammnr 99999\nBilder anbei") == "99999"


def test_parse_body_first_line_hash() -> None:
    assert parse_body_first_line("#12345\nWeitere Infos") == "12345"


def test_parse_body_no_match_in_first_line() -> None:
    assert parse_body_first_line("Hallo\nStammnr 12345") is None


def test_parse_body_empty() -> None:
    assert parse_body_first_line("") is None


def test_parse_attachment_filename_leading_digits() -> None:
    assert parse_attachment_filename("12345_brakes.jpg") == "12345"


def test_parse_attachment_filename_no_digits() -> None:
    assert parse_attachment_filename("photo.jpg") is None


def test_parse_attachment_filename_empty() -> None:
    assert parse_attachment_filename("") is None


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


def test_extract_returns_none_when_no_attachments() -> None:
    msg = _msg(subject="Hallo", body="kein hinweis")
    assert extract_registration_number(msg) is None


def test_parser_class_wraps_extract() -> None:
    parser = EmailSubjectParser()
    msg = _msg(subject="Stammnr 12345")
    assert parser.extract_registration_number(msg) == "12345"
