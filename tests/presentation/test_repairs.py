from fastapi.testclient import TestClient
from ulid import ULID

from edelrep.presentation.container import Container


def _seed_vehicle(container: Container) -> None:
    container.create_vehicle.execute(registration_number="12345", vin=None, description=None)


def test_new_repair_form_renders(client: TestClient, container: Container) -> None:
    _seed_vehicle(container)
    r = client.get("/vehicles/12345/repairs/new")
    assert r.status_code == 200
    assert "Beschreibung" in r.text or "Reparatur" in r.text


def test_new_repair_form_for_missing_vehicle_returns_404(client: TestClient) -> None:
    r = client.get("/vehicles/99999/repairs/new")
    assert r.status_code == 404


def test_create_repair_redirects_to_vehicle_detail(client: TestClient, container: Container) -> None:
    _seed_vehicle(container)
    r = client.post(
        "/vehicles/12345/repairs",
        data={"description": "brakes", "date": "2026-05-03"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/vehicles/12345"


def test_create_repair_for_missing_vehicle_returns_404(client: TestClient) -> None:
    r = client.post(
        "/vehicles/99999/repairs",
        data={"description": "brakes", "date": "2026-05-03"},
    )
    assert r.status_code == 404


def test_create_repair_invalid_date_returns_400(client: TestClient, container: Container) -> None:
    _seed_vehicle(container)
    r = client.post(
        "/vehicles/12345/repairs",
        data={"description": "brakes", "date": "not-a-date"},
    )
    assert r.status_code == 400


def test_repair_appears_on_vehicle_detail(client: TestClient, container: Container) -> None:
    _seed_vehicle(container)
    client.post(
        "/vehicles/12345/repairs",
        data={"description": "brakes", "date": "2026-05-03"},
    )
    r = client.get("/vehicles/12345")
    assert "brakes" in r.text
    assert "2026-05-03" in r.text


def test_create_repair_with_invalid_vehicle_id_returns_404(client: TestClient) -> None:
    """A POST to repairs for an invalid VehicleId (contains $) should return 404."""
    r = client.post(
        "/vehicles/with$dollar/repairs",
        data={"description": "brakes", "date": "2026-05-03"},
    )
    assert r.status_code == 404


def test_create_repair_with_json_accept_returns_201_and_repair_id(
    client: TestClient, container: Container
) -> None:
    _seed_vehicle(container)
    r = client.post(
        "/vehicles/12345/repairs",
        data={"description": "brakes", "date": "2026-05-03"},
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    assert r.status_code == 201
    body = r.json()
    assert "repair_id" in body
    assert body["vehicle_url"] == "/vehicles/12345"
    # repair_id must be parseable as a ULID.
    ULID.from_str(body["repair_id"])


def test_create_repair_with_json_accept_invalid_date_returns_400_json(
    client: TestClient, container: Container
) -> None:
    _seed_vehicle(container)
    r = client.post(
        "/vehicles/12345/repairs",
        data={"description": "brakes", "date": "not-a-date"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 400
    assert "error" in r.json()


def test_create_repair_with_json_accept_missing_vehicle_returns_404_json(
    client: TestClient,
) -> None:
    r = client.post(
        "/vehicles/99999/repairs",
        data={"description": "brakes", "date": "2026-05-03"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 404
    assert "error" in r.json()
