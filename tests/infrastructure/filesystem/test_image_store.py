from pathlib import Path

import pytest
from ulid import ULID

from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
from edelrep.domain.exceptions import ImageNotFound, RepairNotFound
from edelrep.domain.ports import ImageRepository
from edelrep.infrastructure.filesystem.image_store import FilesystemImageRepository
from edelrep.infrastructure.filesystem.repair_store import FilesystemRepairRepository
from edelrep.infrastructure.filesystem.vehicle_store import FilesystemVehicleRepository

from .conftest import make_image  # type: ignore[import-not-found]


def _seed(root: Path, vehicle: Vehicle, repair: Repair) -> None:
    FilesystemVehicleRepository(root).save(vehicle)
    FilesystemRepairRepository(root).save(repair)


def test_save_writes_image_bytes_and_thumbnail(
    storage_root: Path,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(storage_root, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(storage_root)
    img = make_image(sample_repair.id)
    repo.save(img, raw_bytes=sample_image_bytes, thumbnail_bytes=sample_image_bytes)
    repair_path = storage_root / "12345" / "2026-04-15__bremsbelage-vorne"
    image_files = sorted(p.name for p in repair_path.iterdir() if p.is_file())
    assert any(name.startswith("0001_") for name in image_files)
    thumbs = sorted((repair_path / "_thumbs").iterdir())
    assert len(thumbs) == 1


def test_save_raises_when_repair_missing(
    storage_root: Path,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    FilesystemVehicleRepository(storage_root).save(sample_vehicle)
    # Note: repair NOT saved.
    repo = FilesystemImageRepository(storage_root)
    img = make_image(sample_repair.id)
    with pytest.raises(RepairNotFound):
        repo.save(img, raw_bytes=sample_image_bytes)


def test_save_no_thumbnail(
    storage_root: Path,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(storage_root, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(storage_root)
    img = make_image(sample_repair.id)
    repo.save(img, raw_bytes=sample_image_bytes)
    repair_path = storage_root / "12345" / "2026-04-15__bremsbelage-vorne"
    assert not (repair_path / "_thumbs").exists()


def test_save_falls_back_to_bin_extension_for_extensionless_filename(
    storage_root: Path,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(storage_root, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(storage_root)
    iid = ULID()
    img = make_image(sample_repair.id, image_id=iid)
    img_no_ext = Image(
        id=img.id,
        repair_id=img.repair_id,
        storage_key=img.storage_key,
        thumbnail_key=img.thumbnail_key,
        filename="no_extension",
        mime_type=img.mime_type,
        size_bytes=img.size_bytes,
        source=img.source,
        uploaded_at=img.uploaded_at,
        captured_at=img.captured_at,
    )
    repo.save(img_no_ext, raw_bytes=sample_image_bytes)
    repair_path = storage_root / "12345" / "2026-04-15__bremsbelage-vorne"
    files = list(repair_path.iterdir())
    image_files = [p for p in files if p.is_file() and not p.name.startswith("_")]
    assert len(image_files) == 1
    assert image_files[0].suffix == ".bin"


def test_list_for_repair_returns_uploaded_images_in_order(
    storage_root: Path,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(storage_root, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(storage_root)
    first = make_image(sample_repair.id)
    second = make_image(sample_repair.id)
    repo.save(first, raw_bytes=sample_image_bytes)
    repo.save(second, raw_bytes=sample_image_bytes)
    listed = list(repo.list_for_repair(sample_repair.id))
    assert [img.filename.split("_")[0] for img in listed] == ["0001", "0002"]


def test_list_for_repair_skips_thumb_subfolder(
    storage_root: Path,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(storage_root, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(storage_root)
    repo.save(
        make_image(sample_repair.id),
        raw_bytes=sample_image_bytes,
        thumbnail_bytes=sample_image_bytes,
    )
    listed = list(repo.list_for_repair(sample_repair.id))
    assert len(listed) == 1
    assert "_thumbs" not in listed[0].storage_key


def test_list_for_repair_returns_empty_for_unknown(storage_root: Path) -> None:
    repo = FilesystemImageRepository(storage_root)
    assert list(repo.list_for_repair(ULID())) == []


def test_get_returns_image(
    storage_root: Path,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    _seed(storage_root, sample_vehicle, sample_repair)
    repo = FilesystemImageRepository(storage_root)
    img = make_image(sample_repair.id)
    repo.save(img, raw_bytes=sample_image_bytes)
    fetched = repo.get(img.id)
    assert fetched.id == img.id
    assert fetched.repair_id == img.repair_id
    assert fetched.size_bytes == len(sample_image_bytes)
    # Phase 2 always returns MANUAL on read; this is documented behaviour.
    assert fetched.source == ImageSource.MANUAL


def test_get_raises_when_missing(storage_root: Path) -> None:
    repo = FilesystemImageRepository(storage_root)
    with pytest.raises(ImageNotFound):
        repo.get(ULID())


def test_list_for_repair_returns_empty_when_root_missing(tmp_path: Path) -> None:
    repo = FilesystemImageRepository(tmp_path / "nonexistent")
    assert list(repo.list_for_repair(ULID())) == []


def test_get_raises_when_root_missing(tmp_path: Path) -> None:
    repo = FilesystemImageRepository(tmp_path / "nonexistent")
    with pytest.raises(ImageNotFound):
        repo.get(ULID())


def test_save_skips_when_repair_dir_has_no_sidecar(
    storage_root: Path,
    sample_vehicle: Vehicle,
    sample_repair: Repair,
    sample_image_bytes: bytes,
) -> None:
    FilesystemVehicleRepository(storage_root).save(sample_vehicle)
    # Create a repair-shaped dir but without _repair.json — _find_repair_dir must skip it.
    bogus = storage_root / "12345" / "2026-04-15__no-sidecar"
    bogus.mkdir()
    repo = FilesystemImageRepository(storage_root)
    img = make_image(sample_repair.id)
    with pytest.raises(RepairNotFound):
        repo.save(img, raw_bytes=sample_image_bytes)


def test_satisfies_protocol(storage_root: Path) -> None:
    repo: ImageRepository = FilesystemImageRepository(storage_root)
    assert isinstance(repo, ImageRepository)
