import io
from datetime import date

from fastapi.testclient import TestClient
from PIL import Image as PILImage
from ulid import ULID

from edelrep.domain.value_objects import VehicleId
from edelrep.presentation.container import Container


def _make_jpeg() -> bytes:
    img = PILImage.new("RGB", (200, 100), color=(0, 100, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _seed_repair(container: Container) -> str:
    container.create_vehicle.execute(registration_number="12345", vin=None, description=None)
    repair = container.create_repair.execute(
        vehicle_id=VehicleId("12345"),
        repair_date=date(2026, 5, 3),
        description="brakes",
    )
    return str(repair.id)


def test_upload_form_renders(client: TestClient, container: Container) -> None:
    repair_id = _seed_repair(container)
    r = client.get(f"/vehicles/12345/repairs/{repair_id}/upload")
    assert r.status_code == 200
    assert "Bild" in r.text or "Datei" in r.text or "Hochladen" in r.text


def test_upload_image_redirects_to_vehicle_detail(client: TestClient, container: Container) -> None:
    repair_id = _seed_repair(container)
    jpeg = _make_jpeg()
    r = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("photo.jpg", jpeg, "image/jpeg")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/vehicles/12345"


def test_upload_image_for_missing_repair_returns_404(client: TestClient, container: Container) -> None:
    container.create_vehicle.execute(registration_number="12345", vin=None, description=None)
    jpeg = _make_jpeg()
    r = client.post(
        "/vehicles/12345/repairs/01J9TGZP6X2K0V3W7Y8Z4QABCD/images",
        files={"image": ("photo.jpg", jpeg, "image/jpeg")},
    )
    assert r.status_code == 404


def test_get_image_raw_returns_bytes(client: TestClient, container: Container) -> None:
    repair_id = _seed_repair(container)
    jpeg = _make_jpeg()
    client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("photo.jpg", jpeg, "image/jpeg")},
    )
    # Find the saved image's id via list_for_repair.
    images = list(container.image_repo.list_for_repair(ULID.from_str(repair_id)))
    assert len(images) == 1
    image_id = images[0].id

    r = client.get(f"/images/{image_id}/raw")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")
    assert len(r.content) > 0


def test_get_image_thumbnail_returns_bytes(client: TestClient, container: Container) -> None:
    repair_id = _seed_repair(container)
    jpeg = _make_jpeg()
    client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("photo.jpg", jpeg, "image/jpeg")},
    )
    images = list(container.image_repo.list_for_repair(ULID.from_str(repair_id)))
    image_id = images[0].id

    r = client.get(f"/images/{image_id}/thumbnail")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")


def test_get_missing_image_raw_returns_404(client: TestClient) -> None:
    r = client.get("/images/01J9TGZP6X2K0V3W7Y8Z4QABCD/raw")
    assert r.status_code == 404


def test_get_missing_image_thumbnail_returns_404(client: TestClient) -> None:
    r = client.get("/images/01J9TGZP6X2K0V3W7Y8Z4QABCD/thumbnail")
    assert r.status_code == 404


def test_upload_non_image_returns_422(client: TestClient, container: Container) -> None:
    repair_id = _seed_repair(container)
    r = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("photo.jpg", b"this is not an image", "image/jpeg")},
    )
    assert r.status_code == 422
