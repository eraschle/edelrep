from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ulid import ULID

from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
from edelrep.infrastructure.filesystem.sidecar import write_sidecar
from edelrep.infrastructure.watcher.live_index import LiveIndex
from tests.application.fakes import (
    InMemoryImageRepo,
    InMemoryRepairRepo,
    InMemoryVehicleRepo,
)

# Fixed valid ULIDs (Crockford base32, 26 chars) used as on-disk path segments
# so layout regexes and ULID.from_str parsing succeed.
VEHICLE_ID = ULID.from_str("01J9TGZP6X2K0V3W7Y8Z4QFFFF")
VEHICLE_ID_STR = str(VEHICLE_ID)
OTHER_VEHICLE_ID = ULID.from_str("01HXKBP3MGT7VWE5R4QABCDEF1")
OTHER_VEHICLE_ID_STR = str(OTHER_VEHICLE_ID)
REPAIR_ID = ULID.from_str("01J9TGZP6X2K0V3W7Y8Z4QREPA")
REPAIR_ID_STR = str(REPAIR_ID)


def _mock_projector() -> MagicMock:
    proj = MagicMock()
    proj.connection = MagicMock()
    return proj


@pytest.fixture
def live(tmp_path: Path) -> LiveIndex:
    storage_root = tmp_path / "store"
    storage_root.mkdir()
    return LiveIndex(
        storage_root=storage_root,
        projector=_mock_projector(),
        vehicle_repo=InMemoryVehicleRepo(),
        repair_repo=InMemoryRepairRepo(),
        image_repo=InMemoryImageRepo(),
    )


def _proj(live: LiveIndex) -> MagicMock:
    """Return the projector as MagicMock for assertion calls."""
    return live._projector  # type: ignore[return-value]


def test_handle_vehicle_upserts_when_sidecar_exists(live: LiveIndex, tmp_path: Path) -> None:
    storage_root = tmp_path / "store"
    sidecar = storage_root / VEHICLE_ID_STR / "_vehicle.json"
    sidecar.parent.mkdir()
    sidecar.write_text('{"schema_version": 1}', encoding="utf-8")
    vehicle = Vehicle(
        id=VEHICLE_ID,
        registration_number="12345",
        vin="W",
        description="x",
        created_at=datetime(2026, 5, 3, tzinfo=UTC),
    )
    live._vehicle_repo.save(vehicle)  # type: ignore[union-attr]
    live._apply_batch({f"{VEHICLE_ID_STR}/_vehicle.json"})
    _proj(live).upsert_vehicle.assert_called_once_with(vehicle)


def test_handle_vehicle_removes_when_sidecar_missing(live: LiveIndex) -> None:
    live._apply_batch({f"{VEHICLE_ID_STR}/_vehicle.json"})
    _proj(live).remove_vehicle.assert_called_once_with(VEHICLE_ID)


def test_handle_vehicle_removes_when_repo_raises_not_found(live: LiveIndex, tmp_path: Path) -> None:
    storage_root = tmp_path / "store"
    sidecar = storage_root / VEHICLE_ID_STR / "_vehicle.json"
    sidecar.parent.mkdir()
    sidecar.write_text('{"schema_version": 1}', encoding="utf-8")
    # vehicle_repo is empty — get() will raise VehicleNotFound.
    live._apply_batch({f"{VEHICLE_ID_STR}/_vehicle.json"})
    _proj(live).remove_vehicle.assert_called_once_with(VEHICLE_ID)


def test_handle_repair_skips_when_sidecar_missing(live: LiveIndex) -> None:
    live._apply_batch({f"{VEHICLE_ID_STR}/2026-04-15__brakes/_repair.json"})
    _proj(live).upsert_repair.assert_not_called()


def test_handle_repair_skips_when_vehicle_unknown(live: LiveIndex, tmp_path: Path) -> None:
    storage_root = tmp_path / "store"
    sidecar = storage_root / VEHICLE_ID_STR / "2026-04-15__brakes" / "_repair.json"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text('{"schema_version": 1}', encoding="utf-8")
    # vehicle_repo is empty — get() raises VehicleNotFound; nothing is upserted.
    live._apply_batch({f"{VEHICLE_ID_STR}/2026-04-15__brakes/_repair.json"})
    _proj(live).upsert_repair.assert_not_called()


def test_handle_repair_upserts_all_repairs_for_vehicle(live: LiveIndex, tmp_path: Path) -> None:
    storage_root = tmp_path / "store"
    sidecar = storage_root / VEHICLE_ID_STR / "2026-04-15__brakes" / "_repair.json"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text('{"schema_version": 1}', encoding="utf-8")
    vehicle = Vehicle(
        id=VEHICLE_ID,
        registration_number="12345",
        vin="W",
        description="x",
        created_at=datetime(2026, 5, 3, tzinfo=UTC),
    )
    live._vehicle_repo.save(vehicle)  # type: ignore[union-attr]
    repair = Repair(
        id=ULID(),
        vehicle_id=VEHICLE_ID,
        date=date(2026, 4, 15),
        description="brakes",
        created_at=datetime(2026, 5, 3, tzinfo=UTC),
    )
    live._repair_repo.save(repair)  # type: ignore[union-attr]
    live._apply_batch({f"{VEHICLE_ID_STR}/2026-04-15__brakes/_repair.json"})
    assert _proj(live).upsert_repair.call_count == 1


def test_handle_image_skips_when_vehicle_unknown(live: LiveIndex) -> None:
    live._apply_batch(
        {f"{VEHICLE_ID_STR}/2026-04-15__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg"}
    )
    _proj(live).upsert_image.assert_not_called()


def test_handle_image_upserts_all_images_for_repair(live: LiveIndex, tmp_path: Path) -> None:
    storage_root = tmp_path / "store"
    vehicle = Vehicle(
        id=VEHICLE_ID,
        registration_number="12345",
        vin="W",
        description="x",
        created_at=datetime(2026, 5, 3, tzinfo=UTC),
    )
    live._vehicle_repo.save(vehicle)  # type: ignore[union-attr]
    repair = Repair(
        id=ULID(),
        vehicle_id=VEHICLE_ID,
        date=date(2026, 4, 15),
        description="brakes",
        created_at=datetime(2026, 5, 3, tzinfo=UTC),
    )
    live._repair_repo.save(repair)  # type: ignore[union-attr]
    # Write the sidecar file so the repair can be resolved by ID
    sidecar = storage_root / VEHICLE_ID_STR / "2026-04-15__brakes" / "_repair.json"
    sidecar.parent.mkdir(parents=True)
    write_sidecar(
        sidecar,
        {
            "id": str(repair.id),
            "date": "2026-04-15",
            "description": "brakes",
            "created_at": "2026-05-03T00:00:00+00:00",
        },
    )
    image = Image(
        id=ULID(),
        repair_id=repair.id,
        storage_key="placeholder",
        thumbnail_key=None,
        filename="0001.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime(2026, 5, 3, tzinfo=UTC),
        captured_at=None,
    )
    live._image_repo.save(  # type: ignore[union-attr]
        image, raw_bytes=b"\xff\xd8\xff\xd9"
    )
    live._apply_batch(
        {f"{VEHICLE_ID_STR}/2026-04-15__brakes/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg"}
    )
    _proj(live).upsert_image.assert_called()


def test_apply_batch_swallows_errors_per_key(live: LiveIndex) -> None:
    # Force the projector to raise on upsert; the batch must continue.
    _proj(live).remove_vehicle.side_effect = RuntimeError("simulated")
    live._apply_batch(
        {
            f"{VEHICLE_ID_STR}/_vehicle.json",
            f"{OTHER_VEHICLE_ID_STR}/_vehicle.json",
        }
    )
    # Both calls attempted despite the exception.
    assert _proj(live).remove_vehicle.call_count == 2


def test_start_when_already_running_is_noop(tmp_path: Path) -> None:
    storage_root = tmp_path / "store"
    storage_root.mkdir()
    live = LiveIndex(
        storage_root=storage_root,
        projector=_mock_projector(),
        vehicle_repo=InMemoryVehicleRepo(),
        repair_repo=InMemoryRepairRepo(),
        image_repo=InMemoryImageRepo(),
    )
    with (
        patch("edelrep.infrastructure.watcher.live_index.Observer") as mock_observer_cls,
        patch.object(live._drift_detector, "is_drifted", return_value=False),  # type: ignore[arg-type]
    ):
        live.start()
        live.start()  # second call is no-op
        # Observer should be instantiated exactly once.
        assert mock_observer_cls.call_count == 1
    live.stop()


def test_handle_image_matches_repair_by_sidecar_after_description_edit(
    live: LiveIndex, tmp_path: Path
) -> None:
    """After a description edit the folder slug diverges; images must still match
    their repair via the repair-ULID in the folder's _repair.json sidecar."""
    storage_root = tmp_path / "store"
    # Folder name reflects the ORIGINAL slug; the repair's description was since edited.
    dir_name = "2026-04-15__old-slug"
    sidecar = storage_root / VEHICLE_ID_STR / dir_name / "_repair.json"
    sidecar.parent.mkdir(parents=True)
    write_sidecar(
        sidecar,
        {
            "id": REPAIR_ID_STR,
            "date": "2026-04-15",
            "description": "neue beschreibung",
            "created_at": "2026-05-03T00:00:00+00:00",
        },
    )
    live._vehicle_repo.save(  # type: ignore[union-attr]
        Vehicle(
            id=VEHICLE_ID,
            registration_number="12345",
            vin="W",
            description="x",
            created_at=datetime(2026, 5, 3, tzinfo=UTC),
        )
    )
    live._repair_repo.save(  # type: ignore[union-attr]
        Repair(
            id=REPAIR_ID,
            vehicle_id=VEHICLE_ID,
            date=date(2026, 4, 15),
            description="neue beschreibung",
            created_at=datetime(2026, 5, 3, tzinfo=UTC),
        )
    )
    image = Image(
        id=ULID(),
        repair_id=REPAIR_ID,
        storage_key="placeholder",
        thumbnail_key=None,
        filename="0001.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime(2026, 5, 3, tzinfo=UTC),
        captured_at=None,
    )
    live._image_repo.save(image, raw_bytes=b"\xff\xd8\xff\xd9")  # type: ignore[union-attr]

    live._apply_batch(
        {f"{VEHICLE_ID_STR}/{dir_name}/0001_01J9TGZP6X2K0V3W7Y8Z4QABCD.jpg"}
    )

    _proj(live).upsert_image.assert_called()
