from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ulid import ULID

from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
from edelrep.domain.exceptions import ImageNotFound, RepairNotFound
from edelrep.domain.ports import ImageRepository, StorageBackend
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.filesystem.layout import repair_dir_name
from edelrep.infrastructure.storage import LocalFilesystemBackend

from .conftest import make_image  # type: ignore[import-not-found]


def _seed_vehicle(vehicle_repo: FilesystemVehicleRepository) -> Vehicle:
    vehicle = Vehicle(
        id=VehicleId("12345"),
        vin=None,
        description=None,
        created_at=datetime.now(UTC),
    )
    vehicle_repo.save(vehicle)
    return vehicle


def _seed_repair(repair_repo: FilesystemRepairRepository, vehicle_id: VehicleId) -> Repair:
    repair = Repair(
        id=ULID(),
        vehicle_id=vehicle_id,
        date=date(2026, 5, 10),
        description="brakes",
        created_at=datetime.now(UTC),
    )
    repair_repo.save(repair)
    return repair


def _seed(backend: StorageBackend, vehicle: Vehicle, repair: Repair) -> None:
    FilesystemVehicleRepository(backend).save(vehicle)
    FilesystemRepairRepository(backend).save(repair)


def test_save_writes_image_bytes_and_thumbnail(
    backend: StorageBackend,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(backend, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(backend)
    img = make_image(sample_repair.id)
    repo.save(img, raw_bytes=sample_image_bytes, thumbnail_bytes=sample_image_bytes)
    keys = sorted(backend.list_prefix("12345/2026-04-15__bremsbelage-vorne/"))
    image_keys = [k for k in keys if k.endswith(".jpg") and "_thumbs/" not in k]
    thumb_keys = [k for k in keys if "/_thumbs/" in k]
    assert len(image_keys) == 1
    assert image_keys[0].rsplit("/", 1)[1].startswith("0001_")
    assert len(thumb_keys) == 1


def test_save_raises_when_repair_missing(
    backend: StorageBackend,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    FilesystemVehicleRepository(backend).save(sample_vehicle)
    repo = FilesystemImageRepository(backend)
    img = make_image(sample_repair.id)
    with pytest.raises(RepairNotFound):
        repo.save(img, raw_bytes=sample_image_bytes)


def test_save_no_thumbnail(
    backend: StorageBackend,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(backend, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(backend)
    img = make_image(sample_repair.id)
    repo.save(img, raw_bytes=sample_image_bytes)
    thumbs = [k for k in backend.list_prefix("12345/2026-04-15__bremsbelage-vorne/") if "/_thumbs/" in k]
    assert thumbs == []


def test_save_falls_back_to_bin_extension_for_extensionless_filename(
    backend: StorageBackend,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(backend, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(backend)
    iid = ULID()
    template = make_image(sample_repair.id, image_id=iid)
    img_no_ext = Image(
        id=template.id,
        repair_id=template.repair_id,
        storage_key=template.storage_key,
        thumbnail_key=template.thumbnail_key,
        filename="no_extension",
        mime_type=template.mime_type,
        size_bytes=template.size_bytes,
        source=template.source,
        uploaded_at=template.uploaded_at,
        captured_at=template.captured_at,
    )
    repo.save(img_no_ext, raw_bytes=sample_image_bytes)
    keys = [k for k in backend.list_prefix("12345/2026-04-15__bremsbelage-vorne/") if k.endswith(".bin")]
    assert len(keys) == 1


def test_list_for_repair_returns_uploaded_images_in_order(
    backend: StorageBackend,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(backend, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(backend)
    first = make_image(sample_repair.id)
    second = make_image(sample_repair.id)
    repo.save(first, raw_bytes=sample_image_bytes)
    repo.save(second, raw_bytes=sample_image_bytes)
    listed = list(repo.list_for_repair(sample_repair.id))
    assert [img.filename.split("_")[0] for img in listed] == ["0001", "0002"]


def test_list_for_repair_skips_thumb_subfolder(
    backend: StorageBackend,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(backend, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(backend)
    repo.save(
        make_image(sample_repair.id),
        raw_bytes=sample_image_bytes,
        thumbnail_bytes=sample_image_bytes,
    )
    listed = list(repo.list_for_repair(sample_repair.id))
    assert len(listed) == 1
    assert "_thumbs" not in listed[0].storage_key


def test_list_for_repair_returns_empty_for_unknown(backend: StorageBackend) -> None:
    repo = FilesystemImageRepository(backend)
    assert list(repo.list_for_repair(ULID())) == []


def test_get_returns_image(
    backend: StorageBackend,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(backend, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(backend)
    img = make_image(sample_repair.id)
    repo.save(img, raw_bytes=sample_image_bytes)
    fetched = repo.get(img.id)
    assert fetched.id == img.id
    assert fetched.repair_id == img.repair_id
    assert fetched.size_bytes == len(sample_image_bytes)
    # Phase 3 read-time defaults (documented):
    assert fetched.source == ImageSource.MANUAL
    assert fetched.captured_at is None


def test_get_raises_when_missing(backend: StorageBackend) -> None:
    repo = FilesystemImageRepository(backend)
    with pytest.raises(ImageNotFound):
        repo.get(ULID())


def test_save_skips_when_repair_dir_has_no_sidecar(
    backend: StorageBackend,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    FilesystemVehicleRepository(backend).save(sample_vehicle)
    # Seed a key that LOOKS like a repair folder shape but has no _repair.json.
    # _find_repair_path scans _repair.json sidecars only; this should miss → RepairNotFound.
    backend.write_bytes("12345/2026-04-15__no-sidecar/something.txt", b"")
    repo = FilesystemImageRepository(backend)
    img = make_image(sample_repair.id)
    with pytest.raises(RepairNotFound):
        repo.save(img, raw_bytes=sample_image_bytes)


def test_satisfies_protocol(backend: StorageBackend) -> None:
    repo: ImageRepository = FilesystemImageRepository(backend)
    assert isinstance(repo, ImageRepository)


def test_save_persists_comment_in_sidecar(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path)
    vehicle_repo = FilesystemVehicleRepository(backend)
    repair_repo = FilesystemRepairRepository(backend)
    image_repo = FilesystemImageRepository(backend)
    vehicle = _seed_vehicle(vehicle_repo)
    repair = _seed_repair(repair_repo, vehicle.id)

    img = Image(
        id=ULID(),
        repair_id=repair.id,
        storage_key="",
        thumbnail_key=None,
        filename="x.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime.now(UTC),
        captured_at=None,
        comment="brakes left front",
    )
    image_repo.save(img, raw_bytes=b"\x00\x00\x00\x00")

    sidecar_path = (
        tmp_path / "12345" / repair_dir_name(repair.date, repair.description) / f"0001_{img.id!s}.json"
    )
    assert sidecar_path.is_file()


def test_reconstruct_reads_comment_when_sidecar_present(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path)
    vehicle_repo = FilesystemVehicleRepository(backend)
    repair_repo = FilesystemRepairRepository(backend)
    image_repo = FilesystemImageRepository(backend)
    vehicle = _seed_vehicle(vehicle_repo)
    repair = _seed_repair(repair_repo, vehicle.id)

    img = Image(
        id=ULID(),
        repair_id=repair.id,
        storage_key="",
        thumbnail_key=None,
        filename="x.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime.now(UTC),
        captured_at=None,
        comment="hello world",
    )
    image_repo.save(img, raw_bytes=b"\x00\x00\x00\x00")
    reread = image_repo.get(img.id)
    assert reread.comment == "hello world"


def test_save_without_comment_writes_no_sidecar(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path)
    vehicle_repo = FilesystemVehicleRepository(backend)
    repair_repo = FilesystemRepairRepository(backend)
    image_repo = FilesystemImageRepository(backend)
    vehicle = _seed_vehicle(vehicle_repo)
    repair = _seed_repair(repair_repo, vehicle.id)

    img = Image(
        id=ULID(),
        repair_id=repair.id,
        storage_key="",
        thumbnail_key=None,
        filename="x.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime.now(UTC),
        captured_at=None,
    )
    image_repo.save(img, raw_bytes=b"\x00\x00\x00\x00")

    expected_dir = tmp_path / "12345" / repair_dir_name(repair.date, repair.description)
    json_files = [p for p in expected_dir.iterdir() if p.suffix == ".json" and p.name != "_repair.json"]
    assert json_files == []


def test_update_comment_writes_sidecar(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path)
    vehicle_repo = FilesystemVehicleRepository(backend)
    repair_repo = FilesystemRepairRepository(backend)
    image_repo = FilesystemImageRepository(backend)
    vehicle = _seed_vehicle(vehicle_repo)
    repair = _seed_repair(repair_repo, vehicle.id)

    img = Image(
        id=ULID(),
        repair_id=repair.id,
        storage_key="",
        thumbnail_key=None,
        filename="x.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime.now(UTC),
        captured_at=None,
    )
    image_repo.save(img, raw_bytes=b"\x00\x00\x00\x00")
    image_repo.update_comment(img.id, "added later")
    assert image_repo.get(img.id).comment == "added later"


def test_update_comment_with_none_removes_sidecar(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path)
    vehicle_repo = FilesystemVehicleRepository(backend)
    repair_repo = FilesystemRepairRepository(backend)
    image_repo = FilesystemImageRepository(backend)
    vehicle = _seed_vehicle(vehicle_repo)
    repair = _seed_repair(repair_repo, vehicle.id)

    img = Image(
        id=ULID(),
        repair_id=repair.id,
        storage_key="",
        thumbnail_key=None,
        filename="x.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime.now(UTC),
        captured_at=None,
        comment="initial",
    )
    image_repo.save(img, raw_bytes=b"\x00\x00\x00\x00")
    image_repo.update_comment(img.id, None)
    assert image_repo.get(img.id).comment is None
    sidecar_path = (
        tmp_path / "12345" / repair_dir_name(repair.date, repair.description) / f"0001_{img.id!s}.json"
    )
    assert not sidecar_path.exists()


def test_update_comment_unknown_image_raises(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path)
    image_repo = FilesystemImageRepository(backend)
    with pytest.raises(ImageNotFound):
        image_repo.update_comment(ULID(), "x")


def test_list_for_repair_does_not_duplicate_image_for_comment_sidecar(tmp_path: Path) -> None:
    """Regression: a per-image comment sidecar `NNNN_<ulid>.json` must not
    be re-discovered as an image. Otherwise the vehicle detail page shows
    the same thumbnail twice for any image that has a comment."""
    backend = LocalFilesystemBackend(tmp_path)
    vehicle_repo = FilesystemVehicleRepository(backend)
    repair_repo = FilesystemRepairRepository(backend)
    image_repo = FilesystemImageRepository(backend)
    vehicle = _seed_vehicle(vehicle_repo)
    repair = _seed_repair(repair_repo, vehicle.id)

    img = Image(
        id=ULID(),
        repair_id=repair.id,
        storage_key="",
        thumbnail_key=None,
        filename="x.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime.now(UTC),
        captured_at=None,
        comment="brakes",
    )
    image_repo.save(img, raw_bytes=b"\x00\x00\x00\x00")

    images = list(image_repo.list_for_repair(repair.id))
    assert len(images) == 1
    assert images[0].comment == "brakes"


def test_save_sequence_skips_when_prior_image_has_comment(tmp_path: Path) -> None:
    """Regression: per-image sidecars must not inflate the existing-image
    count, otherwise sequence numbers jump on subsequent uploads."""
    backend = LocalFilesystemBackend(tmp_path)
    vehicle_repo = FilesystemVehicleRepository(backend)
    repair_repo = FilesystemRepairRepository(backend)
    image_repo = FilesystemImageRepository(backend)
    vehicle = _seed_vehicle(vehicle_repo)
    repair = _seed_repair(repair_repo, vehicle.id)

    img1 = Image(
        id=ULID(),
        repair_id=repair.id,
        storage_key="",
        thumbnail_key=None,
        filename="a.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime.now(UTC),
        captured_at=None,
        comment="first",
    )
    image_repo.save(img1, raw_bytes=b"\x00\x00\x00\x01")
    img2 = Image(
        id=ULID(),
        repair_id=repair.id,
        storage_key="",
        thumbnail_key=None,
        filename="b.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime.now(UTC),
        captured_at=None,
    )
    image_repo.save(img2, raw_bytes=b"\x00\x00\x00\x02")

    dir_path = tmp_path / "12345" / repair_dir_name(repair.date, repair.description)
    jpg_files = sorted(p.name for p in dir_path.iterdir() if p.suffix == ".jpg")
    assert jpg_files == [f"0001_{img1.id!s}.jpg", f"0002_{img2.id!s}.jpg"]
