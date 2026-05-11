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


def test_vehicle_detail_modal_initially_hidden_without_flex_conflict(
    client: TestClient, container: Container
) -> None:
    """Regression: Tailwind's `.flex` overrides the HTML `hidden` attribute,
    so the modal must use the `hidden` utility class (not the attribute) for
    its initial closed state. Combining `class="...flex..."` with the
    `hidden` attribute makes the modal silently visible from page load."""
    import re

    container.create_vehicle.execute(registration_number="12345", vin=None, description=None)
    r = client.get("/vehicles/12345")
    assert r.status_code == 200

    modal_match = re.search(r'<div id="image-modal"[^>]*>', r.text)
    assert modal_match, "modal element not found in rendered HTML"
    modal_tag = modal_match.group(0)

    classes_match = re.search(r'class="([^"]*)"', modal_tag)
    assert classes_match, "modal must have a class attribute"
    classes = classes_match.group(1).split()

    assert "hidden" in classes, "modal must include the `hidden` utility class for its initial state"
    assert "flex" not in classes, (
        "initial modal must not carry `flex` in its class list — it overrides "
        "the `hidden` attribute and leaves the modal visible from page load"
    )
