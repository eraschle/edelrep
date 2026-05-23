import io
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image as PILImage

from edelrep.application.create_vehicle import CreateVehicleUseCase
from edelrep.application.ingest_email import IngestEmailUseCase
from edelrep.domain.ports import EmailAttachment, EmailMessage
from edelrep.infrastructure.email.inbox_store import InboxStore
from edelrep.infrastructure.email.parser import EmailSubjectParser
from edelrep.presentation.container import build_container


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


def _jpeg() -> bytes:
    img = PILImage.new("RGB", (100, 100), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_dod_email_with_attachment_appears_on_vehicle(tmp_path: Path) -> None:
    """DoD: Test-Mail mit Anhang wird verarbeitet, Bild erscheint am Fahrzeug."""
    storage = tmp_path / "store"
    index = tmp_path / "index.db"
    container = build_container(storage, index, with_live_index=False)

    try:
        # Seed a vehicle that the email Stammnr will match.
        cv = CreateVehicleUseCase(container.vehicle_repo, container.search_index)
        cv.execute(registration_number="12345", vin="WDB", description="Kran")

        # Build a synthetic email with Stammnr in subject + JPEG attachment.
        msg = EmailMessage(
            message_id="<test@example.com>",
            from_address="kunde@firma.ch",
            subject="Stammnr 12345 Bremsen vorne",
            received_at=datetime(2026, 5, 3, 14, 30, tzinfo=UTC),
            body_text="Anbei die Fotos.",
            attachments=(EmailAttachment(filename="brake.jpg", mime_type="image/jpeg", content=_jpeg()),),
        )
        inbox = _FakeInbox([msg])

        use_case = IngestEmailUseCase(
            inbox=inbox,
            parser=EmailSubjectParser(),
            vehicle_repo=container.vehicle_repo,
            repair_repo=container.repair_repo,
            create_repair=container.create_repair,
            upload_image=container.upload_image,
            inbox_store=InboxStore(container.backend),
        )
        stats = use_case.execute()

        # Stats sanity.
        assert stats.fetched == 1
        assert stats.routed == 1
        assert stats.parked == 0
        assert stats.skipped == 0
        assert "<test@example.com>" in inbox.processed

        # Vehicle now has a repair.
        vehicle = container.vehicle_repo.find_by_registration("12345")
        assert vehicle is not None
        repairs = list(container.list_repairs.execute(vehicle.id))
        assert len(repairs) == 1
        assert "Bremsen vorne" in repairs[0].description

        # Repair has the image.
        images = list(container.image_repo.list_for_repair(repairs[0].id))
        assert len(images) == 1
        # Note: images[0].source defaults to MANUAL on read (Phase 2 limitation —
        # FilesystemImageRepository can't distinguish source without per-image
        # sidecars). The use case set it to EMAIL on write but it's not persisted.
    finally:
        container.projector.connection.close()


def test_dod_unrouteable_email_is_parked(tmp_path: Path) -> None:
    """Email without a parseable Stammnr lands in _system/inbox/."""
    storage = tmp_path / "store"
    index = tmp_path / "index.db"
    container = build_container(storage, index, with_live_index=False)

    try:
        msg = EmailMessage(
            message_id="<unroutable@example.com>",
            from_address="anon@example.ch",
            subject="Hallo, anbei Bilder",
            received_at=datetime(2026, 5, 3, 14, 30, tzinfo=UTC),
            body_text="Keine Stammnr drin.",
            attachments=(EmailAttachment(filename="x.jpg", mime_type="image/jpeg", content=_jpeg()),),
        )
        inbox = _FakeInbox([msg])
        use_case = IngestEmailUseCase(
            inbox=inbox,
            parser=EmailSubjectParser(),
            vehicle_repo=container.vehicle_repo,
            repair_repo=container.repair_repo,
            create_repair=container.create_repair,
            upload_image=container.upload_image,
            inbox_store=InboxStore(container.backend),
        )
        stats = use_case.execute()
        assert stats.parked == 1
        assert stats.routed == 0
        # Inbox sidecar exists.
        keys = list(container.backend.list_prefix("_system/inbox/"))
        assert any(k.endswith("_inbox.json") for k in keys)
        assert any(k.endswith(".jpg") for k in keys)
    finally:
        container.projector.connection.close()
