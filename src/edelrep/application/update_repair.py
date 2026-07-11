from ulid import ULID

from edelrep.domain.entities import Repair
from edelrep.domain.ports import RepairRepository


class UpdateRepairUseCase:
    """Update an existing repair's description. Date and identity are immutable.

    Mirrors CreateRepairUseCase: writes only through the repository. Index
    consistency is handled by the live watcher / full reindex.
    """

    def __init__(self, repair_repo: RepairRepository) -> None:
        self._repair_repo = repair_repo

    def execute(self, *, repair_id: ULID, description: str | None) -> Repair:
        existing = self._repair_repo.get(repair_id)
        normalised = (description.strip() if description else None) or None
        updated = Repair(
            id=existing.id,
            vehicle_id=existing.vehicle_id,
            date=existing.date,
            description=normalised,
            created_at=existing.created_at,
        )
        self._repair_repo.update(updated)
        return updated
