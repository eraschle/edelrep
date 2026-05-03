from fastapi.testclient import TestClient

from edelrep.presentation.container import Container


def test_search_page_renders(client: TestClient) -> None:
    response = client.get("/search")
    assert response.status_code == 200
    assert "Fahrzeug suchen" in response.text
    assert "Stammnummer oder Rahmennummer" in response.text


def test_suggestions_empty_query_returns_empty_state(client: TestClient) -> None:
    response = client.get("/search/suggestions?q=")
    assert response.status_code == 200
    assert "Keine Fahrzeuge gefunden" in response.text


def test_suggestions_returns_matches(client: TestClient, container: Container) -> None:
    container.create_vehicle.execute(registration_number="12345", vin="WDB123", description="Kran")
    response = client.get("/search/suggestions?q=WDB")
    assert response.status_code == 200
    assert "12345" in response.text
    assert "WDB123" in response.text
