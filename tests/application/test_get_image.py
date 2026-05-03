import io
from datetime import UTC, datetime

import pytest
from ulid import ULID

from edelrep.application.get_image import GetImageUseCase
from edelrep.domain.entities import Image, ImageSource
from edelrep.domain.exceptions import ImageNotFound

from .fakes import InMemoryImageRepo


class _StubBackend:
    def __init__(self, files: dict[str, bytes]) -> None:
        self._files = files

    def read_bytes(self, key: str) -> bytes:
        return self._files[key]

    def write_bytes(self, key: str, data: bytes) -> None:  # pragma: no cover - unused
        self._files[key] = data

    def open_read(self, key: str):  # pragma: no cover - unused
        return io.BytesIO(self._files[key])

    def delete(self, key: str) -> None:  # pragma: no cover - unused
        self._files.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._files

    def list_prefix(self, prefix: str):  # pragma: no cover - unused
        return [k for k in self._files if k.startswith(prefix)]


def _img(image_id: ULID, repair_id: ULID, key: str) -> Image:
    return Image(
        id=image_id,
        repair_id=repair_id,
        storage_key=key,
        thumbnail_key=None,
        filename="x.jpg",
        mime_type="image/jpeg",
        size_bytes=4,
        source=ImageSource.MANUAL,
        uploaded_at=datetime(2026, 5, 3, tzinfo=UTC),
        captured_at=None,
    )


def test_returns_image_and_bytes() -> None:
    repair_id = ULID()
    image_id = ULID()
    storage_key = "12345/2026-05-03__brakes/0001_test.jpg"
    repo = InMemoryImageRepo()
    repo.save(
        _img(image_id, repair_id, storage_key),
        raw_bytes=b"\xff\xd8\xff\xd9",
    )
    fetched = repo.get(image_id)
    backend = _StubBackend({fetched.storage_key: b"\xff\xd8\xff\xd9"})

    use_case = GetImageUseCase(repo, backend)
    image, raw = use_case.execute(image_id)

    assert image.id == image_id
    assert raw == b"\xff\xd8\xff\xd9"


def test_raises_when_missing() -> None:
    repo = InMemoryImageRepo()
    backend = _StubBackend({})
    use_case = GetImageUseCase(repo, backend)
    with pytest.raises(ImageNotFound):
        use_case.execute(ULID())
