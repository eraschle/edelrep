from collections.abc import Iterable, Sequence
from typing import BinaryIO

from ulid import ULID

from edelrep.domain.entities import Image, Repair, Vehicle
from edelrep.domain.exceptions import ImageNotFound
from edelrep.domain.ports import (
    EmailInbox,
    EmailMessage,
    FuzzyMatcher,
    ImageRepository,
    RepairRepository,
    SearchIndex,
    StorageBackend,
    VehicleRepository,
)


class _FakeVehicleRepo:
    def __init__(self) -> None:
        self._store: dict[ULID, Vehicle] = {}

    def get(self, vehicle_id: ULID, *, include_deleted: bool = False) -> Vehicle:
        return self._store[vehicle_id]

    def save(self, vehicle: Vehicle) -> None:
        self._store[vehicle.id] = vehicle

    def update(self, vehicle: Vehicle) -> None:
        self._store[vehicle.id] = vehicle

    def hard_delete(self, vehicle_id: ULID) -> None:
        self._store.pop(vehicle_id, None)

    def list_all(self, *, include_deleted: bool = False) -> Iterable[Vehicle]:
        return list(self._store.values())

    def exists(self, vehicle_id: ULID, *, include_deleted: bool = False) -> bool:
        return vehicle_id in self._store

    def find_by_registration(self, registration_number: str) -> Vehicle | None:
        for v in self._store.values():
            if v.registration_number == registration_number:
                return v
        return None

    def find_by_vin(self, vin: str) -> Vehicle | None:
        for v in self._store.values():
            if v.vin == vin:
                return v
        return None


class _FakeRepairRepo:
    def __init__(self) -> None:
        self._store: dict[ULID, Repair] = {}

    def get(self, repair_id: ULID) -> Repair:
        return self._store[repair_id]

    def save(self, repair: Repair) -> None:
        self._store[repair.id] = repair

    def update(self, repair: Repair) -> None:
        self._store[repair.id] = repair

    def list_for_vehicle(self, vehicle_id: ULID) -> Iterable[Repair]:
        return [r for r in self._store.values() if r.vehicle_id == vehicle_id]


class _FakeImageRepo:
    def __init__(self) -> None:
        self._store: dict[ULID, Image] = {}

    def get(self, image_id: ULID) -> Image:
        return self._store[image_id]

    def save(
        self,
        image: Image,
        *,
        raw_bytes: bytes,
        thumbnail_bytes: bytes | None = None,
    ) -> None:
        self._store[image.id] = image

    def list_for_repair(self, repair_id: ULID) -> Iterable[Image]:
        return [i for i in self._store.values() if i.repair_id == repair_id]

    def update_comment(self, image_id: ULID, comment: str | None) -> None:
        if image_id not in self._store:
            raise ImageNotFound(image_id)
        old = self._store[image_id]
        self._store[image_id] = Image(
            id=old.id,
            repair_id=old.repair_id,
            storage_key=old.storage_key,
            thumbnail_key=old.thumbnail_key,
            filename=old.filename,
            mime_type=old.mime_type,
            size_bytes=old.size_bytes,
            source=old.source,
            uploaded_at=old.uploaded_at,
            captured_at=old.captured_at,
            comment=comment,
        )


class _FakeStorage:
    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    def read_bytes(self, key: str) -> bytes:
        return self._files[key]

    def write_bytes(self, key: str, data: bytes) -> None:
        self._files[key] = data

    def open_read(self, key: str) -> BinaryIO:  # pragma: no cover - structural only
        raise NotImplementedError

    def delete(self, key: str) -> None:
        self._files.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._files

    def list_prefix(self, prefix: str) -> Iterable[str]:
        return [k for k in self._files if k.startswith(prefix)]


class _FakeSearchIndex:
    def __init__(self) -> None:
        self._rows: dict[ULID, Vehicle] = {}

    def search_vehicles(self, query: str, limit: int = 20) -> Iterable[Vehicle]:
        return list(self._rows.values())[:limit]

    def list_vehicles_by_activity(self, limit: int) -> Iterable[Vehicle]:
        return list(self._rows.values())[:limit]

    def upsert_vehicle(self, vehicle: Vehicle) -> None:
        self._rows[vehicle.id] = vehicle

    def remove_vehicle(self, vehicle_id: ULID) -> None:
        self._rows.pop(vehicle_id, None)

    def clear(self) -> None:
        self._rows.clear()


class _FakeInbox:
    def __init__(self, messages: Sequence[EmailMessage] = ()) -> None:
        self._messages = list(messages)
        self.processed: list[str] = []

    def fetch_unread(self, limit: int = 50) -> Iterable[EmailMessage]:
        return self._messages[:limit]

    def mark_processed(self, message_id: str) -> None:
        self.processed.append(message_id)


class _FakeFuzzyMatcher:
    def score(self, query: str, candidate: str) -> float:
        return 100.0 if query == candidate else 0.0


def test_fake_vehicle_repo_satisfies_protocol() -> None:
    repo: VehicleRepository = _FakeVehicleRepo()
    assert isinstance(repo, VehicleRepository)


def test_fake_repair_repo_satisfies_protocol() -> None:
    repo: RepairRepository = _FakeRepairRepo()
    assert isinstance(repo, RepairRepository)


def test_fake_image_repo_satisfies_protocol() -> None:
    repo: ImageRepository = _FakeImageRepo()
    assert isinstance(repo, ImageRepository)


def test_fake_storage_satisfies_protocol() -> None:
    storage: StorageBackend = _FakeStorage()
    assert isinstance(storage, StorageBackend)


def test_fake_search_index_satisfies_protocol() -> None:
    idx: SearchIndex = _FakeSearchIndex()
    assert isinstance(idx, SearchIndex)


def test_fake_inbox_satisfies_protocol() -> None:
    inbox: EmailInbox = _FakeInbox()
    assert isinstance(inbox, EmailInbox)


def test_fake_fuzzy_matcher_satisfies_protocol() -> None:
    matcher: FuzzyMatcher = _FakeFuzzyMatcher()
    assert isinstance(matcher, FuzzyMatcher)
