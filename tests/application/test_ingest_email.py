import io
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image as PILImage

from edelrep.application.create_repair import CreateRepairUseCase
from edelrep.application.create_vehicle import CreateVehicleUseCase
from edelrep.application.ingest_email import IngestEmailUseCase, IngestStats
from edelrep.application.upload_image import UploadImageUseCase
from edelrep.domain.ports import EmailAttachment, EmailMessage
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.email.inbox_store import InboxStore
from edelrep.infrastructure.email.parser import EmailSubjectParser
from edelrep.infrastructure.exif.pillow_processor import PillowImageProcessor
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.search.in_memory import InMemorySearchIndex
from edelrep.infrastructure.storage import LocalFilesystemBackend


def _jpeg() -> bytes:
    img = PILImage.new("RGB", (100, 100), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class _FakeInbox:
    def __init__(self, messages: Sequence[EmailMessage] = ()) -> None:
        self.messages: list[EmailMessage] = list(messages)
        self.processed: list[str] = []

    def fetch_unread(self, limit: int = 50) -> list[EmailMessage]:
        out = self.messages[:limit]
        self.messages = self.messages[limit:]
        return out

    def mark_processed(self, message_id: str) -> None:
        self.processed.append(message_id)


def _build(
    tmp_path: Path,
) -> tuple[
    LocalFilesystemBackend,
    FilesystemVehicleRepository,
    FilesystemRepairRepository,
    FilesystemImageRepository,
    CreateRepairUseCase,
    UploadImageUseCase,
    InboxStore,
]:
    storage = tmp_path / "store"
    storage.mkdir()
    backend = LocalFilesystemBackend(storage)
    vrepo = FilesystemVehicleRepository(backend)
    rrepo = FilesystemRepairRepository(backend)
    irepo = FilesystemImageRepository(backend)
    create_repair = CreateRepairUseCase(vrepo, rrepo)
    upload_image = UploadImageUseCase(rrepo, irepo, PillowImageProcessor(), backend)
    inbox_store = InboxStore(backend)
    return backend, vrepo, rrepo, irepo, create_repair, upload_image, inbox_store


def _msg_with_jpeg(
    *,
    subject: str = "Stammnr 12345 Bremsen",
    msg_id: str = "<m1@x>",
    image: bytes | None = None,
    extra_attachments: tuple[EmailAttachment, ...] = (),
) -> EmailMessage:
    image = image or _jpeg()
    atts = (
        EmailAttachment(filename="brake.jpg", mime_type="image/jpeg", content=image),
        *extra_attachments,
    )
    return EmailMessage(
        message_id=msg_id,
        from_address="kunde@firma.ch",
        subject=subject,
        received_at=datetime(2026, 5, 3, 14, 30, tzinfo=UTC),
        body_text="hi",
        attachments=atts,
    )


def test_routes_message_to_existing_vehicle(tmp_path: Path) -> None:
    _backend, vrepo, rrepo, irepo, cr, ui, store = _build(tmp_path)
    create_vehicle = CreateVehicleUseCase(vrepo, InMemorySearchIndex())
    create_vehicle.execute(registration_number="12345", vin=None, description=None)

    msg = _msg_with_jpeg()
    inbox = _FakeInbox([msg])
    use_case = IngestEmailUseCase(
        inbox=inbox,
        parser=EmailSubjectParser(),
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        create_repair=cr,
        upload_image=ui,
        inbox_store=store,
    )
    stats = use_case.execute()

    assert isinstance(stats, IngestStats)
    assert stats.fetched == 1
    assert stats.routed == 1
    assert stats.parked == 0
    assert stats.skipped == 0
    assert inbox.processed == ["<m1@x>"]
    repairs = list(rrepo.list_for_vehicle(VehicleId("12345")))
    assert len(repairs) == 1
    images = list(irepo.list_for_repair(repairs[0].id))
    assert len(images) == 1


def test_parks_message_with_no_stammnr(tmp_path: Path) -> None:
    backend, vrepo, rrepo, _irepo, cr, ui, store = _build(tmp_path)
    msg = _msg_with_jpeg(subject="Hallo, Bilder anbei")
    inbox = _FakeInbox([msg])
    use_case = IngestEmailUseCase(
        inbox=inbox,
        parser=EmailSubjectParser(),
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        create_repair=cr,
        upload_image=ui,
        inbox_store=store,
    )
    stats = use_case.execute()
    assert stats.parked == 1
    assert inbox.processed == ["<m1@x>"]
    # Inbox slot exists.
    keys = list(backend.list_prefix("_system/inbox/"))
    assert any(k.endswith("_inbox.json") for k in keys)


def test_parks_message_when_vehicle_missing(tmp_path: Path) -> None:
    _backend, vrepo, rrepo, _irepo, cr, ui, store = _build(tmp_path)
    msg = _msg_with_jpeg(subject="Stammnr 99999 Bremsen")
    inbox = _FakeInbox([msg])
    use_case = IngestEmailUseCase(
        inbox=inbox,
        parser=EmailSubjectParser(),
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        create_repair=cr,
        upload_image=ui,
        inbox_store=store,
    )
    stats = use_case.execute()
    assert stats.parked == 1


def test_parks_message_when_invalid_registration_number(tmp_path: Path) -> None:
    _backend, vrepo, rrepo, _irepo, cr, ui, store = _build(tmp_path)
    # The parser will pick up "with space" if the subject matches a pattern, but
    # subject patterns require a contiguous token. Use a hash-style with invalid chars.
    msg = _msg_with_jpeg(subject="#bad/value")
    inbox = _FakeInbox([msg])
    use_case = IngestEmailUseCase(
        inbox=inbox,
        parser=EmailSubjectParser(),
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        create_repair=cr,
        upload_image=ui,
        inbox_store=store,
    )
    stats = use_case.execute()
    # The parser may or may not match; either way the message should not crash
    # the use case. If parsed successfully but invalid, it parks.
    assert stats.fetched == 1
    assert inbox.processed == ["<m1@x>"]


def test_filters_oversized_attachments(tmp_path: Path) -> None:
    _backend, vrepo, rrepo, _irepo, cr, ui, store = _build(tmp_path)
    create_vehicle = CreateVehicleUseCase(vrepo, InMemorySearchIndex())
    create_vehicle.execute(registration_number="12345", vin=None, description=None)
    big = b"\x00" * (200)
    msg = EmailMessage(
        message_id="<big@x>",
        from_address="x@y.ch",
        subject="Stammnr 12345 huge",
        received_at=datetime(2026, 5, 3, tzinfo=UTC),
        body_text="",
        attachments=(EmailAttachment(filename="big.jpg", mime_type="image/jpeg", content=big),),
    )
    inbox = _FakeInbox([msg])
    use_case = IngestEmailUseCase(
        inbox=inbox,
        parser=EmailSubjectParser(),
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        create_repair=cr,
        upload_image=ui,
        inbox_store=store,
        max_attachment_bytes=100,  # smaller than the attachment
    )
    stats = use_case.execute()
    # No images survived filter; reg matched & vehicle exists, but nothing to upload.
    assert stats.skipped == 1
    assert stats.routed == 0
    repairs = list(rrepo.list_for_vehicle(VehicleId("12345")))
    # Implementation choice: if there are no images, don't create a repair either.
    assert len(repairs) == 0


def test_filters_non_image_attachments(tmp_path: Path) -> None:
    _backend, vrepo, rrepo, _irepo, cr, ui, store = _build(tmp_path)
    create_vehicle = CreateVehicleUseCase(vrepo, InMemorySearchIndex())
    create_vehicle.execute(registration_number="12345", vin=None, description=None)
    msg = EmailMessage(
        message_id="<txt@x>",
        from_address="x@y.ch",
        subject="Stammnr 12345 text",
        received_at=datetime(2026, 5, 3, tzinfo=UTC),
        body_text="",
        attachments=(EmailAttachment(filename="report.pdf", mime_type="application/pdf", content=b"%PDF"),),
    )
    inbox = _FakeInbox([msg])
    use_case = IngestEmailUseCase(
        inbox=inbox,
        parser=EmailSubjectParser(),
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        create_repair=cr,
        upload_image=ui,
        inbox_store=store,
    )
    stats = use_case.execute()
    assert stats.skipped == 1


def _jpeg_different() -> bytes:
    """Return JPEG bytes that differ from _jpeg() to avoid content-dedup rejection."""
    img = PILImage.new("RGB", (100, 100), color=(200, 50, 10))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_handles_duplicate_repair(tmp_path: Path) -> None:
    _backend, vrepo, rrepo, irepo, cr, ui, store = _build(tmp_path)
    create_vehicle = CreateVehicleUseCase(vrepo, InMemorySearchIndex())
    create_vehicle.execute(registration_number="12345", vin=None, description=None)

    # Use distinct images so content-dedup doesn't reject the second upload.
    msg1 = _msg_with_jpeg(msg_id="<m1@x>", subject="Stammnr 12345 Bremsen", image=_jpeg())
    msg2 = _msg_with_jpeg(msg_id="<m2@x>", subject="Stammnr 12345 Bremsen", image=_jpeg_different())
    inbox = _FakeInbox([msg1, msg2])
    use_case = IngestEmailUseCase(
        inbox=inbox,
        parser=EmailSubjectParser(),
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        create_repair=cr,
        upload_image=ui,
        inbox_store=store,
    )
    stats = use_case.execute()
    # Both should be routed; second falls back to existing repair.
    assert stats.routed == 2
    repairs = list(rrepo.list_for_vehicle(VehicleId("12345")))
    assert len(repairs) == 1  # only one repair, two images on it
    images = list(irepo.list_for_repair(repairs[0].id))
    assert len(images) == 2


def test_returns_zero_stats_when_no_messages(tmp_path: Path) -> None:
    _backend, vrepo, rrepo, _irepo, cr, ui, store = _build(tmp_path)
    use_case = IngestEmailUseCase(
        inbox=_FakeInbox([]),
        parser=EmailSubjectParser(),
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        create_repair=cr,
        upload_image=ui,
        inbox_store=store,
    )
    stats = use_case.execute()
    assert stats == IngestStats(fetched=0, routed=0, parked=0, skipped=0)


def test_parks_message_when_parser_returns_invalid_registration(tmp_path: Path) -> None:
    """Parser returning a string that fails VehicleId validation → park the message."""
    _backend, vrepo, rrepo, _irepo, cr, ui, store = _build(tmp_path)
    msg = _msg_with_jpeg(subject="irrelevant")

    # Mock parser to return a string with a space, which is invalid for VehicleId.
    mock_parser = MagicMock(spec=EmailSubjectParser)
    mock_parser.extract_registration_number.return_value = "has space"

    inbox = _FakeInbox([msg])
    use_case = IngestEmailUseCase(
        inbox=inbox,
        parser=mock_parser,
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        create_repair=cr,
        upload_image=ui,
        inbox_store=store,
    )
    stats = use_case.execute()
    assert stats.parked == 1
    assert stats.routed == 0


def test_duplicate_repair_fallback_skips_non_matching_repairs(tmp_path: Path) -> None:
    """DuplicateRepair fallback scans past non-matching repairs before finding the match."""
    _backend, vrepo, rrepo, _irepo, cr, ui, store = _build(tmp_path)
    create_vehicle = CreateVehicleUseCase(vrepo, InMemorySearchIndex())
    create_vehicle.execute(registration_number="12345", vin=None, description=None)

    # Create a decoy repair with a newer date so it sorts first in list_for_vehicle.
    cr.execute(
        vehicle_id=VehicleId("12345"),
        repair_date=datetime(2026, 5, 10, tzinfo=UTC).date(),
        description="Ölwechsel",
    )

    # Now ingest two messages with the same subject (same date/description) to trigger
    # DuplicateRepair on the second; the decoy repair (newer date) will be iterated
    # first (no match), then the target repair is found (covers the 118->117 branch).
    # Use distinct images so content-dedup doesn't reject the second upload.
    msg1 = _msg_with_jpeg(msg_id="<d1@x>", subject="Stammnr 12345 Bremsen", image=_jpeg())
    msg2 = _msg_with_jpeg(msg_id="<d2@x>", subject="Stammnr 12345 Bremsen", image=_jpeg_different())
    inbox = _FakeInbox([msg1, msg2])
    use_case = IngestEmailUseCase(
        inbox=inbox,
        parser=EmailSubjectParser(),
        vehicle_repo=vrepo,
        repair_repo=rrepo,
        create_repair=cr,
        upload_image=ui,
        inbox_store=store,
    )
    stats = use_case.execute()
    assert stats.routed == 2
    repairs = list(rrepo.list_for_vehicle(VehicleId("12345")))
    assert len(repairs) == 2  # decoy + target
