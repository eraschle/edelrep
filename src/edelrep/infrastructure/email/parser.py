import re

from edelrep.domain.ports import EmailMessage

_SUBJECT_PATTERNS = [
    re.compile(r"(?i)stamm(?:nummer|nr|n)?[\s:]+(?P<reg>[A-Za-z0-9._-]+)"),
    re.compile(r"#(?P<reg>[A-Za-z0-9][A-Za-z0-9._-]*)"),
]
_FILENAME_LEADING_DIGITS = re.compile(r"^(?P<reg>\d+)")


def parse_subject(subject: str) -> str | None:
    """Extract registration number from a subject line."""
    if not subject:
        return None
    for pattern in _SUBJECT_PATTERNS:
        match = pattern.search(subject)
        if match:
            return match.group("reg")
    return None


def parse_body_first_line(body: str) -> str | None:
    """Extract registration number from the first line of the body only."""
    if not body:
        return None
    first_line = body.splitlines()[0] if body.splitlines() else body
    for pattern in _SUBJECT_PATTERNS:
        match = pattern.search(first_line)
        if match:
            return match.group("reg")
    return None


def parse_attachment_filename(filename: str) -> str | None:
    """Extract leading digit run from an attachment filename."""
    if not filename:
        return None
    match = _FILENAME_LEADING_DIGITS.match(filename)
    return match.group("reg") if match else None


def extract_registration_number(message: EmailMessage) -> str | None:
    """Try subject, then first body line, then any attachment filename."""
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
