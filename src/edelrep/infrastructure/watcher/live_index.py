import logging
from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.observers import Observer

from edelrep.domain.exceptions import RepairNotFound, VehicleNotFound
from edelrep.domain.ports import (
    ImageRepository,
    RepairRepository,
    VehicleRepository,
)
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.layout import repair_dir_name
from edelrep.infrastructure.index.projector import SqliteIndexProjector
from edelrep.infrastructure.watcher.debouncer import Debouncer
from edelrep.infrastructure.watcher.drift import DriftDetector
from edelrep.infrastructure.watcher.event_handler import KeyEventHandler
from edelrep.infrastructure.watcher.key_mapper import EntityKind, classify

if TYPE_CHECKING:
    from watchdog.observers.api import BaseObserver

_logger = logging.getLogger(__name__)


class LiveIndex:
    """Wires watchdog events to the SQLite projector with debouncing.

    Local-FS only — fsspec backends are unsupported (no filesystem events).
    """

    def __init__(
        self,
        storage_root: Path,
        projector: SqliteIndexProjector,
        vehicle_repo: VehicleRepository,
        repair_repo: RepairRepository,
        image_repo: ImageRepository,
        debounce_seconds: float = 0.3,
    ) -> None:
        self._storage_root = storage_root
        self._projector = projector
        self._vehicle_repo = vehicle_repo
        self._repair_repo = repair_repo
        self._image_repo = image_repo
        self._debouncer = Debouncer(window_seconds=debounce_seconds, on_flush=self._apply_batch)
        self._handler = KeyEventHandler(storage_root, self._debouncer)
        self._observer: BaseObserver | None = None
        self._drift_detected = False
        self._drift_detector = DriftDetector(projector.connection, storage_root)

    @property
    def drift_detected(self) -> bool:
        return self._drift_detected

    def is_running(self) -> bool:
        return self._observer is not None

    def start(self) -> None:
        if self._observer is not None:
            return
        self._drift_detected = self._drift_detector.is_drifted()
        self._storage_root.mkdir(parents=True, exist_ok=True)
        observer = Observer()
        observer.schedule(self._handler, str(self._storage_root), recursive=True)
        observer.start()
        self._observer = observer

    def stop(self) -> None:
        if self._observer is None:
            return
        self._debouncer.stop()
        self._observer.stop()
        self._observer.join(timeout=2.0)
        self._observer = None

    def _apply_batch(self, keys: set[str]) -> None:
        for key in keys:
            kind = classify(key)
            try:
                if kind is EntityKind.VEHICLE:
                    self._handle_vehicle(key)
                elif kind is EntityKind.REPAIR:
                    self._handle_repair(key)
                elif kind is EntityKind.IMAGE:
                    self._handle_image(key)
            except Exception:  # watcher must not crash on individual key
                _logger.exception("watcher: failed to apply key %r", key)
                continue

    def _handle_vehicle(self, key: str) -> None:
        reg_no = key.split("/", 1)[0]
        vid = VehicleId(reg_no)
        if not (self._storage_root / reg_no / "_vehicle.json").is_file():
            self._projector.remove_vehicle(vid)
            return
        try:
            vehicle = self._vehicle_repo.get(vid)
        except VehicleNotFound:
            self._projector.remove_vehicle(vid)
            return
        self._projector.upsert_vehicle(vehicle)

    def _handle_repair(self, key: str) -> None:
        reg_no, dir_name, _ = key.split("/", 2)
        sidecar_path = self._storage_root / reg_no / dir_name / "_repair.json"
        if not sidecar_path.is_file():
            return
        try:
            vehicle = self._vehicle_repo.get(VehicleId(reg_no))
        except VehicleNotFound:
            return
        for repair in self._repair_repo.list_for_vehicle(vehicle.id):
            self._projector.upsert_repair(repair)

    def _handle_image(self, key: str) -> None:
        reg_no, dir_name, _ = key.split("/", 2)
        try:
            vehicle = self._vehicle_repo.get(VehicleId(reg_no))
        except VehicleNotFound:
            return
        for repair in self._repair_repo.list_for_vehicle(vehicle.id):
            if repair_dir_name(repair.date, repair.description) != dir_name:
                continue
            try:
                images = list(self._image_repo.list_for_repair(repair.id))
            except RepairNotFound:
                return
            for image in images:
                self._projector.upsert_image(image)
            return
