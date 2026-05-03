from edelrep.domain.ports import (
    ImageRepository,
    RepairRepository,
    VehicleRepository,
)
from edelrep.infrastructure.index.projector import (
    ReindexStats,
    SqliteIndexProjector,
)


class ReindexUseCase:
    """Rebuild the SQLite index cache from filesystem state."""

    def __init__(
        self,
        projector: SqliteIndexProjector,
        vehicle_repo: VehicleRepository,
        repair_repo: RepairRepository,
        image_repo: ImageRepository,
    ) -> None:
        self._projector = projector
        self._vehicle_repo = vehicle_repo
        self._repair_repo = repair_repo
        self._image_repo = image_repo

    def execute(self) -> ReindexStats:
        return self._projector.full_rebuild(
            self._vehicle_repo,
            self._repair_repo,
            self._image_repo,
        )
