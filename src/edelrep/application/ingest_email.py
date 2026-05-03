from dataclasses import dataclass

from ulid import ULID

from edelrep.application.create_repair import CreateRepairUseCase
from edelrep.application.upload_image import UploadImageUseCase
from edelrep.domain.entities import ImageSource
from edelrep.domain.exceptions import (
    DuplicateRepair,
    InvalidVehicleId,
    VehicleNotFound,
)
from edelrep.domain.ports import (
    EmailInbox,
    EmailMessage,
    RepairRepository,
    VehicleRepository,
)
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.email.inbox_store import InboxStore
from edelrep.infrastructure.email.parser import EmailSubjectParser
from edelrep.infrastructure.filesystem.layout import repair_dir_name


@dataclass(frozen=True, slots=True)
class IngestStats:
    fetched: int = 0
    routed: int = 0
    parked: int = 0
    skipped: int = 0


class IngestEmailUseCase:
    """Pull unread email, route image attachments to vehicles, park the rest."""

    def __init__(
        self,
        *,
        inbox: EmailInbox,
        parser: EmailSubjectParser,
        vehicle_repo: VehicleRepository,
        repair_repo: RepairRepository,
        create_repair: CreateRepairUseCase,
        upload_image: UploadImageUseCase,
        inbox_store: InboxStore,
        max_attachment_bytes: int = 25 * 1024 * 1024,
    ) -> None:
        self._inbox = inbox
        self._parser = parser
        self._vehicle_repo = vehicle_repo
        self._repair_repo = repair_repo
        self._create_repair = create_repair
        self._upload_image = upload_image
        self._inbox_store = inbox_store
        self._max_bytes = max_attachment_bytes

    def execute(self, *, limit: int = 50) -> IngestStats:
        fetched = routed = parked = skipped = 0
        for message in self._inbox.fetch_unread(limit=limit):
            fetched += 1
            try:
                outcome = self._handle_message(message)
            finally:
                self._inbox.mark_processed(message.message_id)
            if outcome == "routed":
                routed += 1
            elif outcome == "parked":
                parked += 1
            else:
                skipped += 1
        return IngestStats(fetched=fetched, routed=routed, parked=parked, skipped=skipped)

    def _handle_message(self, message: EmailMessage) -> str:
        images = [
            a
            for a in message.attachments
            if a.mime_type.startswith("image/") and len(a.content) <= self._max_bytes
        ]
        reg = self._parser.extract_registration_number(message)
        if reg is None:
            self._inbox_store.park(message)
            return "parked"
        try:
            vehicle_id = VehicleId(reg)
        except InvalidVehicleId:
            self._inbox_store.park(message)
            return "parked"
        try:
            self._vehicle_repo.get(vehicle_id)
        except VehicleNotFound:
            self._inbox_store.park(message)
            return "parked"
        if not images:
            return "skipped"
        repair_id = self._get_or_create_repair_id(message, vehicle_id)
        for att in images:
            self._upload_image.execute(
                repair_id=repair_id,
                raw_bytes=att.content,
                filename=att.filename or "email.jpg",
                source=ImageSource.EMAIL,
            )
        return "routed"

    def _get_or_create_repair_id(self, message: EmailMessage, vehicle_id: VehicleId) -> ULID:
        repair_date = message.received_at.date()
        description = message.subject or "E-Mail"
        try:
            repair = self._create_repair.execute(
                vehicle_id=vehicle_id,
                repair_date=repair_date,
                description=description,
            )
            return repair.id
        except DuplicateRepair:
            target_dir_name = repair_dir_name(repair_date, description)
            for r in self._repair_repo.list_for_vehicle(vehicle_id):
                if repair_dir_name(r.date, r.description) == target_dir_name:
                    return r.id
            raise  # should be unreachable; if duplicate, the matching repair exists
