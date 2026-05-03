from pathlib import Path

import pytest

from edelrep.infrastructure.storage.factory import build_storage_backend
from edelrep.infrastructure.storage.fsspec_backend import FsspecBackend
from edelrep.infrastructure.storage.local_filesystem import LocalFilesystemBackend


def test_local_backend(tmp_path: Path) -> None:
    backend = build_storage_backend({"mode": "local", "root": str(tmp_path / "store")})
    assert isinstance(backend, LocalFilesystemBackend)


def test_fsspec_memory_backend() -> None:
    backend = build_storage_backend(
        {"mode": "fsspec", "fsspec": {"protocol": "memory", "root": "/edelrep-factory-test"}}
    )
    assert isinstance(backend, FsspecBackend)


def test_unknown_mode_rejected() -> None:
    with pytest.raises(ValueError, match="mode"):
        build_storage_backend({"mode": "carrier-pigeon", "root": "/x"})


def test_local_requires_root() -> None:
    with pytest.raises(ValueError, match="root"):
        build_storage_backend({"mode": "local"})


def test_fsspec_requires_protocol() -> None:
    with pytest.raises(ValueError, match="protocol"):
        build_storage_backend({"mode": "fsspec", "fsspec": {"root": "/x"}})


def test_fsspec_requires_root() -> None:
    with pytest.raises(ValueError, match="root"):
        build_storage_backend({"mode": "fsspec", "fsspec": {"protocol": "memory"}})


def test_local_creates_root_if_missing(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "store"
    assert not target.exists()
    build_storage_backend({"mode": "local", "root": str(target)})
    assert target.is_dir()
