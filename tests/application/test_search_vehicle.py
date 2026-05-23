from datetime import UTC, datetime

import pytest
from ulid import ULID

from edelrep.application.search_vehicle import SearchVehicleUseCase
from edelrep.domain.entities import Vehicle


class _FakeIndex:
    def __init__(self, vehicles: list[Vehicle]) -> None:
        self._vehicles = vehicles

    def search_vehicles(self, query: str, limit: int = 20):  # pragma: no cover - not used
        return []

    def list_vehicles_by_activity(self, limit: int):
        return self._vehicles[:limit]

    def upsert_vehicle(self, vehicle: Vehicle) -> None: ...

    def remove_vehicle(self, vehicle_id: ULID) -> None: ...

    def clear(self) -> None: ...


class _AlwaysMaxMatcher:
    def score(self, query: str, candidate: str) -> float:
        return 100.0 if candidate else 0.0


class _NeverMatcher:
    def score(self, query: str, candidate: str) -> float:
        return 0.0


def _vehicle(reg: str, vin: str | None = None, desc: str | None = None) -> Vehicle:
    return Vehicle(
        id=ULID(),
        registration_number=reg,
        vin=vin,
        description=desc,
        created_at=datetime.now(UTC),
    )


def test_empty_query_returns_activity_list() -> None:
    vs = [_vehicle("AAA"), _vehicle("BBB")]
    uc = SearchVehicleUseCase(_FakeIndex(vs), _NeverMatcher())
    assert uc.execute("") == vs


def test_whitespace_only_query_returns_activity_list() -> None:
    vs = [_vehicle("AAA")]
    uc = SearchVehicleUseCase(_FakeIndex(vs), _NeverMatcher())
    assert uc.execute("   ") == vs


def test_query_with_high_score_returns_results() -> None:
    vs = [_vehicle("AAA"), _vehicle("BBB")]
    uc = SearchVehicleUseCase(_FakeIndex(vs), _AlwaysMaxMatcher())
    result = uc.execute("ZZZ")
    assert {v.registration_number for v in result} == {"AAA", "BBB"}


def test_query_below_threshold_returns_empty() -> None:
    vs = [_vehicle("AAA")]
    uc = SearchVehicleUseCase(_FakeIndex(vs), _NeverMatcher())
    assert uc.execute("anything") == []


def test_limit_zero_raises() -> None:
    uc = SearchVehicleUseCase(_FakeIndex([]), _NeverMatcher())
    with pytest.raises(ValueError):
        uc.execute("", limit=0)
