from datetime import UTC, datetime

import pytest

from edelrep.application.search_vehicle import SearchVehicleUseCase
from edelrep.domain.entities import Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.search.in_memory import InMemorySearchIndex


def _v(reg: str) -> Vehicle:
    return Vehicle(
        id=VehicleId(reg),
        vin="W",
        description="x",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_search_returns_matching_vehicles() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345"))
    idx.upsert_vehicle(_v("67890"))
    use_case = SearchVehicleUseCase(idx)
    results = use_case.execute("123")
    assert [v.id.registration_number for v in results] == ["12345"]


def test_empty_query_returns_empty_list() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345"))
    use_case = SearchVehicleUseCase(idx)
    assert use_case.execute("") == []


def test_limit_must_be_positive() -> None:
    idx = InMemorySearchIndex()
    use_case = SearchVehicleUseCase(idx)
    with pytest.raises(ValueError, match="limit"):
        use_case.execute("any", limit=0)


def test_limit_passes_through_to_index() -> None:
    idx = InMemorySearchIndex()
    for i in range(5):
        idx.upsert_vehicle(_v(f"1234{i}"))
    use_case = SearchVehicleUseCase(idx)
    results = use_case.execute("1234", limit=2)
    assert len(results) == 2
