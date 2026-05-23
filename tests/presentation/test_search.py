from datetime import UTC, datetime

from fastapi.testclient import TestClient
from ulid import ULID

from edelrep.domain.entities import Vehicle
from edelrep.presentation.container import Container


def test_search_page_renders(client: TestClient) -> None:
    response = client.get("/search")
    assert response.status_code == 200
    assert "Fahrzeug suchen" in response.text
    assert "Stammnummer" in response.text


def test_suggestions_empty_query_returns_empty_state(client: TestClient) -> None:
    response = client.get("/search/suggestions?q=")
    assert response.status_code == 200
    assert "Noch keine Fahrzeuge angelegt" in response.text


def test_suggestions_returns_matches(client: TestClient, container: Container) -> None:
    container.create_vehicle.execute(registration_number="12345", vin="WDB123", description="Kran")
    response = client.get("/search/suggestions?q=WDB")
    assert response.status_code == 200
    assert "12345" in response.text
    assert "WDB123" in response.text


def test_search_page_initial_renders_all_vehicles(client: TestClient, container: Container) -> None:
    container.vehicle_repo.save(
        Vehicle(
            id=ULID(),
            registration_number="AAA",
            vin=None,
            description=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    container.vehicle_repo.save(
        Vehicle(
            id=ULID(),
            registration_number="BBB",
            vin=None,
            description=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    container.projector.full_rebuild(container.vehicle_repo, container.repair_repo, container.image_repo)
    r = client.get("/search")
    assert r.status_code == 200
    body = r.text
    assert "AAA" in body
    assert "BBB" in body


def test_search_suggestions_empty_query_returns_all(client: TestClient, container: Container) -> None:
    container.vehicle_repo.save(
        Vehicle(
            id=ULID(),
            registration_number="XYZ",
            vin=None,
            description=None,
            created_at=datetime.now(UTC),
        )
    )
    container.projector.full_rebuild(container.vehicle_repo, container.repair_repo, container.image_repo)
    r = client.get("/search/suggestions?q=")
    assert r.status_code == 200
    assert "XYZ" in r.text


def test_search_suggestions_fuzzy_typo_finds_vehicle(client: TestClient, container: Container) -> None:
    container.vehicle_repo.save(
        Vehicle(
            id=ULID(),
            registration_number="12345",
            vin=None,
            description=None,
            created_at=datetime.now(UTC),
        )
    )
    container.projector.full_rebuild(container.vehicle_repo, container.repair_repo, container.image_repo)
    r = client.get("/search/suggestions?q=12354")
    assert r.status_code == 200
    assert "12345" in r.text


def test_search_suggestions_no_matches_message(client: TestClient) -> None:
    r = client.get("/search/suggestions?q=Z9Z9Z9")
    assert r.status_code == 200
    assert "Keine Treffer" in r.text or "Keine Fahrzeuge" in r.text


def test_search_suggestions_finds_by_description_token(
    client: TestClient, container: Container
) -> None:
    """End-to-end regression: searching for a token contained in a vehicle's
    Bezeichnung must surface the vehicle even when the Stammnummer doesn't
    match the query."""
    container.create_vehicle.execute(
        registration_number="12345",
        vin=None,
        description="Kran 4-achsig",
    )
    container.create_vehicle.execute(
        registration_number="99999",
        vin=None,
        description="Lieferwagen",
    )
    container.projector.full_rebuild(
        container.vehicle_repo, container.repair_repo, container.image_repo
    )
    r = client.get("/search/suggestions?q=Kran")
    assert r.status_code == 200
    assert "12345" in r.text
    assert "99999" not in r.text


def test_search_suggestions_finds_by_description_with_typo(
    client: TestClient, container: Container
) -> None:
    """The fuzzy layer must tolerate small typos when matching the Bezeichnung."""
    container.create_vehicle.execute(
        registration_number="55555",
        vin=None,
        description="Lieferwagen mit Hebebühne",
    )
    container.projector.full_rebuild(
        container.vehicle_repo, container.repair_repo, container.image_repo
    )
    r = client.get("/search/suggestions?q=Lieferwgen")  # missing 'a'
    assert r.status_code == 200
    assert "55555" in r.text
