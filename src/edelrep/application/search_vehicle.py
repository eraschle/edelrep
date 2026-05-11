from edelrep.domain.entities import Vehicle
from edelrep.domain.ports import FuzzyMatcher, SearchIndex


class SearchVehicleUseCase:
    """Search vehicles. Empty query returns most-recently-active vehicles."""

    SCORE_THRESHOLD = 60.0
    CANDIDATE_POOL = 1000

    def __init__(self, search_index: SearchIndex, fuzzy: FuzzyMatcher) -> None:
        self._search_index = search_index
        self._fuzzy = fuzzy

    def execute(self, query: str, limit: int = 50) -> list[Vehicle]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        q = query.strip()
        if not q:
            return list(self._search_index.list_vehicles_by_activity(limit))

        candidates = list(self._search_index.list_vehicles_by_activity(self.CANDIDATE_POOL))
        scored: list[tuple[float, int, Vehicle]] = []
        for idx, v in enumerate(candidates):
            best = max(
                self._fuzzy.score(q, v.id.registration_number),
                self._fuzzy.score(q, v.vin or ""),
                self._fuzzy.score(q, v.description or ""),
            )
            if best >= self.SCORE_THRESHOLD:
                scored.append((best, -idx, v))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return [v for _, _, v in scored[:limit]]
