import pytest
from ulid import ULID

from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
from edelrep.domain.exceptions import ImageNotFound, RepairNotFound
from edelrep.domain.ports import ImageRepository, StorageBackend
from edelrep.infrastructure.filesystem.image_store import FilesystemImageRepository
from edelrep.infrastructure.filesystem.repair_store import FilesystemRepairRepository
from edelrep.infrastructure.filesystem.vehicle_store import FilesystemVehicleRepository

from .conftest import make_image  # type: ignore[import-not-found]


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
