from datetime import UTC, datetime

from edelrep.domain.entities import Vehicle
from edelrep.domain.ports import SearchIndex
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.search.in_memory import InMemorySearchIndex


def _v(reg: str, vin: str = "X", description: str = "") -> Vehicle:
    return Vehicle(
        id=VehicleId(reg),
        vin=vin or None,
        description=description or None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_satisfies_protocol() -> None:
    idx: SearchIndex = InMemorySearchIndex()
    assert isinstance(idx, SearchIndex)


def test_empty_query_returns_empty_list() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345"))
    assert list(idx.search_vehicles("")) == []


def test_search_by_registration_number_substring() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345"))
    idx.upsert_vehicle(_v("99999"))
    results = list(idx.search_vehicles("123"))
    assert [v.id.registration_number for v in results] == ["12345"]


def test_search_by_vin_substring() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345", vin="WDB123ABC"))
    idx.upsert_vehicle(_v("99999", vin="VFX9999"))
    results = list(idx.search_vehicles("WDB"))
    assert [v.id.registration_number for v in results] == ["12345"]


def test_search_by_description_substring_case_insensitive() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345", description="Kran 4-achsig"))
    idx.upsert_vehicle(_v("99999", description="Lieferwagen"))
    results = list(idx.search_vehicles("KRAN"))
    assert [v.id.registration_number for v in results] == ["12345"]


def test_search_respects_limit() -> None:
    idx = InMemorySearchIndex()
    for i in range(5):
        idx.upsert_vehicle(_v(f"1234{i}"))
    results = list(idx.search_vehicles("1234", limit=3))
    assert len(results) == 3


def test_upsert_replaces_existing() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345", description="old"))
    idx.upsert_vehicle(_v("12345", description="new"))
    results = list(idx.search_vehicles("new"))
    assert len(results) == 1
    assert results[0].description == "new"


def test_remove_vehicle() -> None:
    idx = InMemorySearchIndex()
    vid = VehicleId("12345")
    idx.upsert_vehicle(_v("12345"))
    idx.remove_vehicle(vid)
    assert list(idx.search_vehicles("123")) == []


def test_remove_missing_is_noop() -> None:
    idx = InMemorySearchIndex()
    idx.remove_vehicle(VehicleId("never-existed"))


def test_clear_empties_index() -> None:
    idx = InMemorySearchIndex()
    idx.upsert_vehicle(_v("12345"))
    idx.upsert_vehicle(_v("99999"))
    idx.clear()
    assert list(idx.search_vehicles("123")) == []
    assert list(idx.search_vehicles("999")) == []
