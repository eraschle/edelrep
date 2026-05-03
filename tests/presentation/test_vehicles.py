from fastapi.testclient import TestClient

from edelrep.presentation.container import Container


def test_new_vehicle_form_renders(client: TestClient) -> None:
    r = client.get("/vehicles/new")
    assert r.status_code == 200
    assert "Stammnummer" in r.text


def test_create_vehicle_redirects_to_detail(client: TestClient) -> None:
    r = client.post("/vehicles", data={"registration_number": "12345"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/vehicles/12345"


def test_create_vehicle_invalid_returns_400(client: TestClient) -> None:
    r = client.post("/vehicles", data={"registration_number": "with space"})
    assert r.status_code == 400


def test_create_vehicle_duplicate_returns_400(client: TestClient, container: Container) -> None:
    container.create_vehicle.execute(registration_number="12345", vin=None, description=None)
    r = client.post("/vehicles", data={"registration_number": "12345"})
    assert r.status_code == 400


def test_vehicle_detail_404(client: TestClient) -> None:
    r = client.get("/vehicles/99999")
    assert r.status_code == 404


def test_vehicle_detail_renders(client: TestClient, container: Container) -> None:
    container.create_vehicle.execute(registration_number="12345", vin="WDB", description="Kran")
    r = client.get("/vehicles/12345")
    assert r.status_code == 200
    assert "12345" in r.text
    assert "WDB" in r.text
    assert "Kran" in r.text
    assert "Rahmennummer" in r.text
