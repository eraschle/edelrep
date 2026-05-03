import os
from dataclasses import dataclass
from pathlib import Path

from edelrep.application.create_repair import CreateRepairUseCase
from edelrep.application.create_vehicle import CreateVehicleUseCase
from edelrep.application.get_image import GetImageUseCase
from edelrep.application.ingest_email import IngestEmailUseCase
from edelrep.application.list_repairs import ListRepairsUseCase
from edelrep.application.search_vehicle import SearchVehicleUseCase
from edelrep.application.upload_image import UploadImageUseCase
from edelrep.domain.ports import (
    ImageRepository,
    RepairRepository,
    SearchIndex,
    StorageBackend,
    VehicleRepository,
)
from edelrep.infrastructure.email.config import EmailConfig
from edelrep.infrastructure.email.imap_adapter import ImapInbox
from edelrep.infrastructure.email.inbox_store import InboxStore
from edelrep.infrastructure.email.parser import EmailSubjectParser
from edelrep.infrastructure.email.poller import EmailPoller
from edelrep.infrastructure.exif.pillow_processor import PillowImageProcessor
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.index import (
    SqliteIndexProjector,
    SqliteSearchIndex,
    open_index_database,
)
from edelrep.infrastructure.storage import LocalFilesystemBackend
from edelrep.infrastructure.watcher.live_index import LiveIndex


@dataclass
class Container:
    """Composition root holding all wired components."""

    backend: StorageBackend
    vehicle_repo: VehicleRepository
    repair_repo: RepairRepository
    image_repo: ImageRepository
    search_index: SearchIndex
    projector: SqliteIndexProjector
    create_vehicle: CreateVehicleUseCase
    create_repair: CreateRepairUseCase
    upload_image: UploadImageUseCase
    list_repairs: ListRepairsUseCase
    get_image: GetImageUseCase
    search_vehicle: SearchVehicleUseCase
    live_index: LiveIndex | None = None
    email_poller: EmailPoller | None = None


def build_container(
    storage_root: Path,
    index_path: Path | str,
    *,
    with_live_index: bool = True,
    debounce_seconds: float = 0.3,
    email_config: EmailConfig | None = None,
) -> Container:
    """Wire a full Container against the local filesystem and SQLite."""
    storage_root.mkdir(parents=True, exist_ok=True)

    backend = LocalFilesystemBackend(storage_root)
    vehicle_repo = FilesystemVehicleRepository(backend)
    repair_repo = FilesystemRepairRepository(backend)
    image_repo = FilesystemImageRepository(backend)

    if isinstance(index_path, Path):
        index_path.parent.mkdir(parents=True, exist_ok=True)
    conn = open_index_database(index_path)
    projector = SqliteIndexProjector(conn)
    search_index = SqliteSearchIndex(conn)

    processor = PillowImageProcessor()

    container = Container(
        backend=backend,
        vehicle_repo=vehicle_repo,
        repair_repo=repair_repo,
        image_repo=image_repo,
        search_index=search_index,
        projector=projector,
        create_vehicle=CreateVehicleUseCase(vehicle_repo, search_index),
        create_repair=CreateRepairUseCase(vehicle_repo, repair_repo),
        upload_image=UploadImageUseCase(repair_repo, image_repo, processor),
        list_repairs=ListRepairsUseCase(vehicle_repo, repair_repo),
        get_image=GetImageUseCase(image_repo, backend),
        search_vehicle=SearchVehicleUseCase(search_index),
    )

    if with_live_index:
        container.live_index = LiveIndex(
            storage_root=storage_root,
            projector=projector,
            vehicle_repo=vehicle_repo,
            repair_repo=repair_repo,
            image_repo=image_repo,
            debounce_seconds=debounce_seconds,
        )

    if email_config is not None and email_config.enabled:
        password = os.environ.get(email_config.password_env)
        if not password:
            raise RuntimeError(f"environment variable {email_config.password_env!r} is empty or unset")
        imap_inbox = ImapInbox(
            host=email_config.host,
            user=email_config.user,
            password=password,
            folder=email_config.folder,
        )
        ingest_use_case = IngestEmailUseCase(
            inbox=imap_inbox,
            parser=EmailSubjectParser(),
            vehicle_repo=vehicle_repo,
            repair_repo=repair_repo,
            create_repair=container.create_repair,
            upload_image=container.upload_image,
            inbox_store=InboxStore(backend),
            max_attachment_bytes=email_config.max_attachment_mb * 1024 * 1024,
        )
        container.email_poller = EmailPoller(
            use_case=ingest_use_case,
            interval_seconds=float(email_config.poll_interval_seconds),
        )

    return container
