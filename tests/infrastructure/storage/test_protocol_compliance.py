from pathlib import Path

import fsspec
from fsspec.implementations.memory import MemoryFileSystem

from edelrep.domain.ports import StorageBackend
from edelrep.infrastructure.storage import FsspecBackend, LocalFilesystemBackend


def test_local_backend_satisfies_protocol(tmp_path: Path) -> None:
    backend: StorageBackend = LocalFilesystemBackend(tmp_path)
    assert isinstance(backend, StorageBackend)


def test_fsspec_backend_satisfies_protocol() -> None:
    fs = fsspec.filesystem("memory")
    if isinstance(fs, MemoryFileSystem):
        fs.store.clear()
        fs.pseudo_dirs.clear()
    backend: StorageBackend = FsspecBackend(fs, root="/proto-check-2")
    assert isinstance(backend, StorageBackend)
