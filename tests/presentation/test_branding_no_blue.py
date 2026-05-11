"""Regression: after the Edelmann re-brand, slate and blue Tailwind classes
must not reappear in rendered pages. The only exception is the upload
status badge that uses bg-blue-50/text-blue-700/ring-blue-200 to signal
an in-progress upload — these stay as a functional indicator."""
from __future__ import annotations

import re
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from ulid import ULID

from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.presentation.container import Container

ALLOWED_BLUE = {"bg-blue-50", "text-blue-700", "ring-blue-200"}

_BLUE_RE = re.compile(r"(?:^|[\s:\"'])((?:bg|text|ring|border|fill|stroke)-blue-\d+)\b")
_SLATE_RE = re.compile(r"(?:^|[\s:\"'])((?:bg|text|ring|border|fill|stroke)-slate-\d+)\b")


def _find_blue(text: str) -> set[str]:
    return {m.group(1) for m in _BLUE_RE.finditer(text)} - ALLOWED_BLUE


def _find_slate(text: str) -> set[str]:
    return {m.group(1) for m in _SLATE_RE.finditer(text)}


def _seed_full(container: Container) -> None:
    """Create one vehicle + one repair so the detail page is non-trivial."""
    vehicle = Vehicle(
        id=VehicleId("12345"), vin="WDB1", description="Kran",
        created_at=datetime.now(UTC),
    )
    container.vehicle_repo.save(vehicle)
    container.repair_repo.save(Repair(
        id=ULID(), vehicle_id=vehicle.id, date=date(2026, 5, 11),
        description="brakes", created_at=datetime.now(UTC),
    ))
    container.projector.full_rebuild(container.vehicle_repo, container.repair_repo, container.image_repo)


@pytest.mark.parametrize(
    "path",
    [
        "/search",
        "/vehicles/new",
        "/vehicles/12345",
        "/vehicles/12345/repairs/new",
        "/inbox",
    ],
)
def test_page_has_no_disallowed_blue_or_slate_classes(
    client: TestClient, container: Container, path: str
) -> None:
    _seed_full(container)
    r = client.get(path)
    assert r.status_code == 200, f"{path} returned {r.status_code}"
    bad_blue = _find_blue(r.text)
    bad_slate = _find_slate(r.text)
    assert not bad_blue, f"{path} has disallowed blue classes: {sorted(bad_blue)}"
    assert not bad_slate, f"{path} has disallowed slate classes: {sorted(bad_slate)}"
