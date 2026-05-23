from collections.abc import Iterable

from ulid import ULID

from edelrep.domain.entities import Vehicle


class InMemorySearchIndex:
    """Dict-backed SearchIndex implementation.

    Search is case-insensitive substring match across registration_number,
    vin, and description. Empty queries return an empty list.

    Useful both as a test fake and as a dev-mode adapter until Phase 5
    SQLite + FTS5 ships.
    """

    def __init__(self) -> None:
        self._rows: dict[ULID, Vehicle] = {}

    def search_vehicles(self, query: str, limit: int = 20) -> Iterable[Vehicle]:
        if not query:
            return []
        needle = query.lower()
        results: list[Vehicle] = []
        for vehicle in self._rows.values():
            haystack = " ".join(
                str(part)
                for part in (
                    vehicle.registration_number or "",
                    vehicle.vin or "",
                    vehicle.description or "",
                )
            ).lower()
            if needle in haystack:
                results.append(vehicle)
            if len(results) >= limit:
                break
        return results

    def list_vehicles_by_activity(self, limit: int) -> Iterable[Vehicle]:
        return list(self._rows.values())[:limit]

    def upsert_vehicle(self, vehicle: Vehicle) -> None:
        self._rows[vehicle.id] = vehicle

    def remove_vehicle(self, vehicle_id: ULID) -> None:
        self._rows.pop(vehicle_id, None)

    def clear(self) -> None:
        self._rows.clear()
