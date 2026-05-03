from edelrep.domain.entities import Vehicle
from edelrep.domain.ports import SearchIndex


class SearchVehicleUseCase:
    """Search vehicles by registration number, VIN, or description."""

    def __init__(self, search_index: SearchIndex) -> None:
        self._search_index = search_index

    def execute(self, query: str, limit: int = 20) -> list[Vehicle]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        return list(self._search_index.search_vehicles(query, limit=limit))
