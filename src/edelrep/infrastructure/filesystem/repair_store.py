from collections.abc import Iterable
from pathlib import Path

from ulid import ULID

from edelrep.domain.entities import Repair
from edelrep.domain.exceptions import DuplicateRepair, RepairNotFound, VehicleNotFound
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem.json_codec import (
    parse_aware_datetime,
    parse_date,
    parse_ulid,
)
from edelrep.infrastructure.filesystem.layout import (
    REPAIR_DIR_NAME_RE,
    repair_dir_name,
    repair_sidecar_path,
    vehicle_dir,
)
from edelrep.infrastructure.filesystem.sidecar import read_sidecar, write_sidecar


class FilesystemRepairRepository:
    """RepairRepository implementation backed by per-repair sidecars on disk."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def get(self, repair_id: ULID) -> Repair:
        for sidecar, vid in self._iter_sidecars():
            data = read_sidecar(sidecar)
            if parse_ulid(str(data["id"])) == repair_id:
                return self._deserialise(vid, data)
        raise RepairNotFound(repair_id)

    def save(self, repair: Repair) -> None:
        veh_dir = vehicle_dir(self._root, repair.vehicle_id)
        if not veh_dir.is_dir():
            raise VehicleNotFound(repair.vehicle_id.registration_number)
        dir_name = repair_dir_name(repair.date, repair.description)
        target_dir = veh_dir / dir_name
        if target_dir.exists():
            raise DuplicateRepair(repair.vehicle_id.registration_number, dir_name)
        target_dir.mkdir(parents=True)
        write_sidecar(repair_sidecar_path(self._root, repair.vehicle_id, dir_name), self._serialise(repair))

    def update(self, repair: Repair) -> None:
        for sidecar, vid in self._iter_sidecars():
            data = read_sidecar(sidecar)
            if parse_ulid(str(data["id"])) == repair.id and vid == repair.vehicle_id:
                write_sidecar(sidecar, self._serialise(repair))
                return
        raise RepairNotFound(repair.id)

    def list_for_vehicle(self, vehicle_id: VehicleId) -> Iterable[Repair]:
        veh_dir = vehicle_dir(self._root, vehicle_id)
        if not veh_dir.is_dir():
            return
        repairs: list[Repair] = []
        for entry in veh_dir.iterdir():
            if not entry.is_dir() or not REPAIR_DIR_NAME_RE.match(entry.name):
                continue
            sidecar = entry / "_repair.json"
            if not sidecar.is_file():
                continue
            data = read_sidecar(sidecar)
            repairs.append(self._deserialise(vehicle_id, data))
        repairs.sort(key=lambda r: r.date, reverse=True)
        yield from repairs

    def _iter_sidecars(self) -> Iterable[tuple[Path, VehicleId]]:
        if not self._root.is_dir():
            return
        for vdir in self._root.iterdir():
            if not vdir.is_dir() or vdir.name.startswith("_"):
                continue
            try:
                vid = VehicleId(vdir.name)
            except Exception:
                continue
            for rdir in vdir.iterdir():
                if not rdir.is_dir() or not REPAIR_DIR_NAME_RE.match(rdir.name):
                    continue
                sidecar = rdir / "_repair.json"
                if sidecar.is_file():
                    yield sidecar, vid

    @staticmethod
    def _serialise(repair: Repair) -> dict[str, object]:
        return {
            "id": str(repair.id),
            "date": repair.date,
            "description": repair.description,
            "created_at": repair.created_at,
        }

    @staticmethod
    def _deserialise(vehicle_id: VehicleId, data: dict[str, object]) -> Repair:
        return Repair(
            id=parse_ulid(str(data["id"])),
            vehicle_id=vehicle_id,
            date=parse_date(str(data["date"])),
            description=str(data["description"]),
            created_at=parse_aware_datetime(str(data["created_at"])),
        )
