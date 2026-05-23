import io
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from PIL import Image as PILImage
from ulid import ULID

from edelrep.domain.entities import Image, ImageSource
from edelrep.presentation.container import Container


def _make_jpeg() -> bytes:
    img = PILImage.new("RGB", (200, 100), color=(0, 100, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _jpeg_bytes() -> bytes:
    """Alias used by comment-related tests."""
    return _make_jpeg()


def _seed_repair(container: Container) -> str:
    vehicle = container.create_vehicle.execute(
        registration_number="12345", vin=None, description=None
    )
    repair = container.create_repair.execute(
        vehicle_id=vehicle.id,
        repair_date=date(2026, 5, 3),
        description="brakes",
    )
    return str(repair.id)


def _seed_vehicle_and_repair(container: Container, registration_number: str) -> None:
    """Create a vehicle and one repair for the given registration number."""
    vehicle = container.create_vehicle.execute(
        registration_number=registration_number, vin=None, description=None
    )
    container.create_repair.execute(
        vehicle_id=vehicle.id,
        repair_date=date(2026, 5, 3),
        description="brakes",
    )


def _first_repair_id(container: Container, registration_number: str) -> str:
    """Return the string ULID of the first repair for the given vehicle."""
    vehicle = container.vehicle_repo.find_by_registration(registration_number)
    assert vehicle is not None
    repairs = list(container.repair_repo.list_for_vehicle(vehicle.id))
    return str(repairs[0].id)


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


def test_upload_form_for_missing_vehicle_returns_404(client: TestClient) -> None:
    r = client.get("/vehicles/99999/repairs/01J9TGZP6X2K0V3W7Y8Z4QABCD/upload")
    assert r.status_code == 404


def test_upload_form_for_invalid_vehicle_id_returns_404(client: TestClient) -> None:
    r = client.get("/vehicles/with space/repairs/01J9TGZP6X2K0V3W7Y8Z4QABCD/upload")
    # The whitespace registration_number is invalid AND not a 12345-style URL.
    # FastAPI may URL-encode; assert 404 regardless.
    assert r.status_code == 404


def test_upload_image_with_invalid_repair_id_returns_404(client: TestClient, container: Container) -> None:
    container.create_vehicle.execute(registration_number="12345", vin=None, description=None)
    jpeg = _make_jpeg()
    r = client.post(
        "/vehicles/12345/repairs/not-a-ulid/images",
        files={"image": ("photo.jpg", jpeg, "image/jpeg")},
    )
    assert r.status_code == 404


def test_upload_image_with_json_accept_returns_201_and_image_id(
    client: TestClient, container: Container
) -> None:
    repair_id = _seed_repair(container)
    jpeg = _make_jpeg()
    r = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("photo.jpg", jpeg, "image/jpeg")},
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    assert r.status_code == 201
    body = r.json()
    assert "image_id" in body
    ULID.from_str(body["image_id"])


def test_upload_non_image_with_json_accept_returns_422_json(client: TestClient, container: Container) -> None:
    repair_id = _seed_repair(container)
    r = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("photo.jpg", b"this is not an image", "image/jpeg")},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 422
    assert "error" in r.json()


def test_upload_image_missing_repair_with_json_accept_returns_404_json(
    client: TestClient, container: Container
) -> None:
    container.create_vehicle.execute(registration_number="12345", vin=None, description=None)
    jpeg = _make_jpeg()
    r = client.post(
        "/vehicles/12345/repairs/01J9TGZP6X2K0V3W7Y8Z4QABCD/images",
        files={"image": ("photo.jpg", jpeg, "image/jpeg")},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 404
    assert "error" in r.json()


def test_upload_duplicate_image_returns_422_with_german_message(
    client: TestClient, container: Container
) -> None:
    """Uploading the same JPEG twice returns 422 with the German error message."""
    repair_id = _seed_repair(container)
    jpeg = _make_jpeg()

    # First upload succeeds.
    r1 = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("photo.jpg", jpeg, "image/jpeg")},
        headers={"Accept": "application/json"},
    )
    assert r1.status_code == 201

    # Second upload with identical bytes must fail.
    r2 = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("photo_copy.jpg", jpeg, "image/jpeg")},
        headers={"Accept": "application/json"},
    )
    assert r2.status_code == 422
    body = r2.json()
    assert "error" in body
    assert "Identisches Bild" in body["error"]


def test_thumbnail_returns_404_when_image_has_no_thumbnail(client: TestClient, container: Container) -> None:
    """If an image was saved without thumbnail_bytes, the thumbnail endpoint 404s."""
    # Seed via the use case path, then directly save a no-thumbnail image via repo.
    vehicle = container.create_vehicle.execute(
        registration_number="12345", vin=None, description=None
    )
    repair = container.create_repair.execute(
        vehicle_id=vehicle.id,
        repair_date=date(2026, 5, 3),
        description="brakes",
    )
    iid = ULID()
    img = Image(
        id=iid,
        repair_id=repair.id,
        storage_key="placeholder",
        thumbnail_key=None,
        filename="upload.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime(2026, 5, 3, tzinfo=UTC),
        captured_at=None,
    )
    container.image_repo.save(img, raw_bytes=b"\xff\xd8\xff\xd9")
    r = client.get(f"/images/{iid}/thumbnail")
    assert r.status_code == 404


def test_upload_image_with_comment_form_field(client: TestClient, container: Container) -> None:
    _seed_vehicle_and_repair(container, "12345")
    repair_id = _first_repair_id(container, "12345")
    r = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("x.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"comment": "brakes left"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 201
    image_id = r.json()["image_id"]
    img = container.image_repo.get(ULID.from_str(image_id))
    assert img.comment == "brakes left"


def test_patch_image_comment_sets_and_returns_value(client: TestClient, container: Container) -> None:
    _seed_vehicle_and_repair(container, "12345")
    repair_id = _first_repair_id(container, "12345")
    upload = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("x.jpg", _jpeg_bytes(), "image/jpeg")},
        headers={"Accept": "application/json"},
    )
    image_id = upload.json()["image_id"]
    r = client.patch(f"/images/{image_id}/comment", json={"comment": "updated"})
    assert r.status_code == 200
    body = r.json()
    assert body["comment"] == "updated"
    assert container.image_repo.get(ULID.from_str(image_id)).comment == "updated"


def test_patch_image_comment_null_clears(client: TestClient, container: Container) -> None:
    _seed_vehicle_and_repair(container, "12345")
    repair_id = _first_repair_id(container, "12345")
    upload = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("x.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"comment": "initial"},
        headers={"Accept": "application/json"},
    )
    image_id = upload.json()["image_id"]
    r = client.patch(f"/images/{image_id}/comment", json={"comment": None})
    assert r.status_code == 200
    assert r.json()["comment"] is None
    assert container.image_repo.get(ULID.from_str(image_id)).comment is None


def test_patch_image_comment_too_long_returns_422(client: TestClient, container: Container) -> None:
    _seed_vehicle_and_repair(container, "12345")
    repair_id = _first_repair_id(container, "12345")
    upload = client.post(
        f"/vehicles/12345/repairs/{repair_id}/images",
        files={"image": ("x.jpg", _jpeg_bytes(), "image/jpeg")},
        headers={"Accept": "application/json"},
    )
    image_id = upload.json()["image_id"]
    r = client.patch(f"/images/{image_id}/comment", json={"comment": "x" * 1001})
    assert r.status_code == 422


def test_patch_unknown_image_comment_returns_404(client: TestClient) -> None:
    r = client.patch(f"/images/{ULID()!s}/comment", json={"comment": "x"})
    assert r.status_code == 404
