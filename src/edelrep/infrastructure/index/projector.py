import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from ulid import ULID

from edelrep.domain.entities import Image, Repair, Vehicle
from edelrep.domain.ports import (
    ImageRepository,
    RepairRepository,
    VehicleRepository,
)
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.layout import repair_dir_name


@dataclass(frozen=True, slots=True)
class ReindexStats:
    vehicles_indexed: int
    repairs_indexed: int
    images_indexed: int
    duration_seconds: float


class SqliteIndexProjector:
    """Drives full and incremental updates to the SQLite index cache."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def full_rebuild(
        self,
        vehicle_repo: VehicleRepository,
        repair_repo: RepairRepository,
        image_repo: ImageRepository,
    ) -> ReindexStats:
        start = time.perf_counter()
        vehicles_indexed = 0
        repairs_indexed = 0
        images_indexed = 0

        self._conn.execute("BEGIN")
        try:
            self._conn.execute("DELETE FROM images")
            self._conn.execute("DELETE FROM repairs")
            self._conn.execute("DELETE FROM vehicles")
            for vehicle in vehicle_repo.list_all():
                self._insert_vehicle(vehicle)
                vehicles_indexed += 1
                for repair in repair_repo.list_for_vehicle(vehicle.id):
                    self._insert_repair(repair)
                    repairs_indexed += 1
                    for image in image_repo.list_for_repair(repair.id):
                        self._insert_image(image)
                        images_indexed += 1
            self._conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_full_reindex', ?)",
                (datetime.now(UTC).isoformat(),),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return ReindexStats(
            vehicles_indexed=vehicles_indexed,
            repairs_indexed=repairs_indexed,
            images_indexed=images_indexed,
            duration_seconds=time.perf_counter() - start,
        )

    def upsert_vehicle(self, vehicle: Vehicle) -> None:
        self._insert_vehicle(vehicle)

    def upsert_repair(self, repair: Repair) -> None:
        self._insert_repair(repair)

    def upsert_image(self, image: Image) -> None:
        self._insert_image(image)

    def remove_vehicle(self, vehicle_id: VehicleId) -> None:
        self._conn.execute(
            "DELETE FROM vehicles WHERE registration_number = ?",
            (vehicle_id.registration_number,),
        )

    def remove_repair(self, repair_id: ULID) -> None:
        self._conn.execute("DELETE FROM repairs WHERE id = ?", (str(repair_id),))

    def remove_image(self, image_id: ULID) -> None:
        self._conn.execute("DELETE FROM images WHERE id = ?", (str(image_id),))

    def _insert_vehicle(self, vehicle: Vehicle) -> None:
        self._conn.execute(
            """
            INSERT INTO vehicles (registration_number, vin, description, created_at, fs_mtime)
            VALUES (?, ?, ?, ?, NULL)
            ON CONFLICT(registration_number) DO UPDATE SET
                vin = excluded.vin,
                description = excluded.description,
                created_at = excluded.created_at
            """,
            (
                vehicle.id.registration_number,
                vehicle.vin,
                vehicle.description,
                vehicle.created_at.isoformat(),
            ),
        )

    def _insert_repair(self, repair: Repair) -> None:
        folder = repair_dir_name(repair.date, repair.description)
        self._conn.execute(
            """
            INSERT INTO repairs (id, registration_number, date, description, folder_name, fs_mtime)
            VALUES (?, ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                registration_number = excluded.registration_number,
                date = excluded.date,
                description = excluded.description,
                folder_name = excluded.folder_name
            """,
            (
                str(repair.id),
                repair.vehicle_id.registration_number,
                repair.date.isoformat(),
                repair.description,
                folder,
            ),
        )

    def _insert_image(self, image: Image) -> None:
        self._conn.execute(
            """
            INSERT INTO images (id, repair_id, filename, thumb_path, mime_type,
                                size_bytes, exif_taken_at, fs_mtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                repair_id = excluded.repair_id,
                filename = excluded.filename,
                thumb_path = excluded.thumb_path,
                mime_type = excluded.mime_type,
                size_bytes = excluded.size_bytes,
                exif_taken_at = excluded.exif_taken_at
            """,
            (
                str(image.id),
                str(image.repair_id),
                image.filename,
                image.thumbnail_key,
                image.mime_type,
                image.size_bytes,
                image.captured_at.isoformat() if image.captured_at else None,
            ),
        )
