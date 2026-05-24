from datetime import UTC, datetime

import pytest
from ulid import ULID

from edelrep.application.delete_image import DeleteImageUseCase
from edelrep.domain.entities import Image, ImageSource
from edelrep.domain.exceptions import ImageNotFound
from edelrep.infrastructure.search.in_memory import InMemorySearchIndex

from .fakes import InMemoryImageRepo


def _image(*, repair_id: ULID | None = None) -> Image:
    return Image(
        id=ULID(),
        repair_id=repair_id or ULID(),
        storage_key="placeholder",
        thumbnail_key=None,
        filename="0001_test.jpg",
        mime_type="image/jpeg",
        size_bytes=10,
        source=ImageSource.MANUAL,
        uploaded_at=datetime(2026, 5, 1, tzinfo=UTC),
        captured_at=None,
    )


def test_delete_removes_image_from_repo() -> None:
    repo = InMemoryImageRepo()
    img = _image()
    repo.save(img, raw_bytes=b"raw", thumbnail_bytes=None)
    uc = DeleteImageUseCase(repo, InMemorySearchIndex())
    uc.execute(img.id)
    with pytest.raises(ImageNotFound):
        repo.get(img.id)


def test_delete_unknown_image_raises() -> None:
    repo = InMemoryImageRepo()
    uc = DeleteImageUseCase(repo, InMemorySearchIndex())
    with pytest.raises(ImageNotFound):
        uc.execute(ULID())


def test_delete_calls_search_index_remove_image() -> None:
    repo = InMemoryImageRepo()
    img = _image()
    repo.save(img, raw_bytes=b"raw", thumbnail_bytes=None)

    calls: list[ULID] = []

    class _SpyIndex(InMemorySearchIndex):
        def remove_image(self, image_id: ULID) -> None:
            calls.append(image_id)

    uc = DeleteImageUseCase(repo, _SpyIndex())
    uc.execute(img.id)
    assert calls == [img.id]


def test_delete_keeps_sibling_image_intact() -> None:
    repo = InMemoryImageRepo()
    repair_id = ULID()
    keeper = _image(repair_id=repair_id)
    victim = _image(repair_id=repair_id)
    repo.save(keeper, raw_bytes=b"k", thumbnail_bytes=None)
    repo.save(victim, raw_bytes=b"v", thumbnail_bytes=None)
    uc = DeleteImageUseCase(repo, InMemorySearchIndex())
    uc.execute(victim.id)
    remaining = [i.id for i in repo.list_for_repair(repair_id)]
    assert remaining == [keeper.id]
