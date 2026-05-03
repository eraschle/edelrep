import io
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage

from edelrep.domain.value_objects import VehicleId
from edelrep.presentation.app_factory import create_app
from edelrep.presentation.container import Container, build_container


@pytest.fixture
def live_container(tmp_path: Path) -> Iterator[Container]:
    storage = tmp_path / "store"
    index = tmp_path / "index.db"
    c = build_container(storage, index, with_live_index=True, debounce_seconds=0.05)
    yield c
    c.projector.connection.close()


@pytest.fixture
def live_client(live_container: Container) -> Iterator[TestClient]:
    app = create_app(live_container)
    with TestClient(app) as test_client:
        yield test_client


def _make_jpeg() -> bytes:
    img = PILImage.new("RGB", (200, 100), color=(0, 100, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def test_full_click_path(live_client: TestClient, live_container: Container) -> None:
    """DoD: create vehicle → repair → upload → wiederfinden via search."""
    # 1. Create vehicle.
    r = live_client.post(
        "/vehicles",
        data={
            "registration_number": "CRANE001",
            "vin": "WDBLIVE123",
            "description": "Liebherr Mobilkran",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/vehicles/CRANE001"

    # 2. Open detail page.
    r = live_client.get("/vehicles/CRANE001")
    assert r.status_code == 200
    assert "Liebherr" in r.text
    # German label rendered.
    assert "Rahmennummer" in r.text

    # 3. Create repair.
    r = live_client.post(
        "/vehicles/CRANE001/repairs",
        data={"description": "Bremsen", "date": "2026-05-03"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # Get the repair_id by listing repairs (URLs don't include the ULID).
    repairs = list(live_container.list_repairs.execute(VehicleId("CRANE001")))
    assert len(repairs) == 1
    repair_id = str(repairs[0].id)

    # 4. Upload image.
    jpeg = _make_jpeg()
    r = live_client.post(
        f"/vehicles/CRANE001/repairs/{repair_id}/images",
        files={"image": ("photo.jpg", jpeg, "image/jpeg")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # 5. Search for the vehicle (poll up to 10s for the live-index to propagate).
    deadline = time.monotonic() + 10.0
    found = False
    while time.monotonic() < deadline:
        r = live_client.get("/search/suggestions?q=Liebherr")
        if "CRANE001" in r.text:
            found = True
            break
        time.sleep(0.1)
    assert found, "Vehicle did not appear in live search within 10s"

    # 6. Confirm vehicle detail shows the repair AND the thumbnail.
    r = live_client.get("/vehicles/CRANE001")
    assert r.status_code == 200
    assert "Bremsen" in r.text
    assert "2026-05-03" in r.text
    # Thumbnail src should be present in the rendered HTML.
    assert "/thumbnail" in r.text
