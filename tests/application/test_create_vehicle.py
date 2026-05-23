import pytest

from edelrep.application.create_vehicle import CreateVehicleUseCase
from edelrep.domain.exceptions import DuplicateRegistrationNumber, InvalidRegistrationNumber
from edelrep.infrastructure.search.in_memory import InMemorySearchIndex

from .fakes import InMemoryVehicleRepo


def test_creates_vehicle_with_required_fields() -> None:
    repo = InMemoryVehicleRepo()
    idx = InMemorySearchIndex()
    use_case = CreateVehicleUseCase(repo, idx)
    vehicle = use_case.execute(registration_number="12345", vin="WDB", description="Kran")
    assert vehicle.registration_number == "12345"
    assert repo.exists(vehicle.id)


def test_indexes_into_search() -> None:
    repo = InMemoryVehicleRepo()
    idx = InMemorySearchIndex()
    use_case = CreateVehicleUseCase(repo, idx)
    use_case.execute(registration_number="12345", vin="WDB123", description="x")
    hits = list(idx.search_vehicles("WDB"))
    assert len(hits) == 1


def test_optional_vin_and_description() -> None:
    repo = InMemoryVehicleRepo()
    idx = InMemorySearchIndex()
    use_case = CreateVehicleUseCase(repo, idx)
    vehicle = use_case.execute(registration_number="12345", vin=None, description=None)
    assert vehicle.vin is None
    assert vehicle.description is None


def test_empty_string_normalized_to_none() -> None:
    repo = InMemoryVehicleRepo()
    idx = InMemorySearchIndex()
    use_case = CreateVehicleUseCase(repo, idx)
    vehicle = use_case.execute(registration_number="12345", vin="", description="")
    assert vehicle.vin is None
    assert vehicle.description is None


def test_invalid_registration_raises() -> None:
    repo = InMemoryVehicleRepo()
    idx = InMemorySearchIndex()
    use_case = CreateVehicleUseCase(repo, idx)
    with pytest.raises(InvalidRegistrationNumber):
        use_case.execute(registration_number="with spaces", vin=None, description=None)


def test_duplicate_raises() -> None:
    repo = InMemoryVehicleRepo()
    idx = InMemorySearchIndex()
    use_case = CreateVehicleUseCase(repo, idx)
    use_case.execute(registration_number="12345", vin=None, description=None)
    with pytest.raises(DuplicateRegistrationNumber):
        use_case.execute(registration_number="12345", vin=None, description=None)
