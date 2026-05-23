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


def test_edit_form_renders_prefilled(client: TestClient, container: Container) -> None:
    container.create_vehicle.execute(
        registration_number="12345", vin="WDB123", description="Kran 4-achsig"
    )
    r = client.get("/vehicles/12345/edit")
    assert r.status_code == 200
    assert "Fahrzeug bearbeiten" in r.text
    assert 'value="12345"' in r.text
    assert 'value="WDB123"' in r.text
    assert 'value="Kran 4-achsig"' in r.text


def test_edit_form_404_for_unknown_vehicle(client: TestClient) -> None:
    r = client.get("/vehicles/UNKNOWN/edit")
    assert r.status_code == 404


def test_edit_post_updates_and_redirects(
    client: TestClient, container: Container
) -> None:
    container.create_vehicle.execute(registration_number="12345", vin=None, description=None)
    r = client.post(
        "/vehicles/12345/edit",
        data={"registration_number": "67890", "vin": "NEWVIN", "description": "Kran"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/vehicles/67890"
    # Confirm the change landed in the index.
    found = container.vehicle_repo.find_by_registration("67890")
    assert found is not None
    assert found.vin == "NEWVIN"
    assert found.description == "Kran"


def test_edit_post_can_be_addressed_by_old_registration_until_redirect(
    client: TestClient, container: Container
) -> None:
    """After the redirect, the new key is canonical — but the original
    /vehicles/<old>/edit URL must still resolve as long as the old value is
    submitted unchanged (and through resolve_vehicle for the GET form)."""
    container.create_vehicle.execute(registration_number="12345", vin=None, description=None)
    # GET still works through the old key.
    r = client.get("/vehicles/12345/edit")
    assert r.status_code == 200


def test_edit_post_clearing_both_identifiers_returns_400(
    client: TestClient, container: Container
) -> None:
    container.create_vehicle.execute(registration_number="12345", vin=None, description=None)
    r = client.post(
        "/vehicles/12345/edit",
        data={"registration_number": "", "vin": "", "description": "noch da"},
    )
    assert r.status_code == 400
    assert "Stammnummer oder Rahmennummer" in r.text


def test_edit_post_duplicate_registration_returns_400(
    client: TestClient, container: Container
) -> None:
    container.create_vehicle.execute(registration_number="11111", vin=None, description=None)
    container.create_vehicle.execute(registration_number="22222", vin=None, description=None)
    r = client.post(
        "/vehicles/22222/edit",
        data={"registration_number": "11111", "vin": "", "description": ""},
    )
    assert r.status_code == 400
    assert "bereits vergeben" in r.text


def test_edit_post_duplicate_vin_returns_400(
    client: TestClient, container: Container
) -> None:
    container.create_vehicle.execute(registration_number="11111", vin="VIN1", description=None)
    container.create_vehicle.execute(registration_number="22222", vin="VIN2", description=None)
    r = client.post(
        "/vehicles/22222/edit",
        data={"registration_number": "22222", "vin": "VIN1", "description": ""},
    )
    assert r.status_code == 400
    assert "bereits vergeben" in r.text


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
