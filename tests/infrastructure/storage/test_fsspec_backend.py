import fsspec
import pytest
from fsspec.implementations.memory import MemoryFileSystem

from edelrep.domain.ports import StorageBackend
from edelrep.infrastructure.storage.fsspec_backend import FsspecBackend


@pytest.fixture
def backend() -> FsspecBackend:
    fs = fsspec.filesystem("memory")
    if isinstance(fs, MemoryFileSystem):
        fs.store.clear()
        fs.pseudo_dirs.clear()
    return FsspecBackend(fs, root="/edelrep-test")


def test_write_then_read_round_trip(backend: FsspecBackend) -> None:
    backend.write_bytes("a/b/c.txt", b"hello")
    assert backend.read_bytes("a/b/c.txt") == b"hello"


def test_write_creates_parents_implicitly(backend: FsspecBackend) -> None:
    backend.write_bytes("nested/deep/file.bin", b"x")
    assert backend.exists("nested/deep/file.bin")


def test_write_overwrites(backend: FsspecBackend) -> None:
    backend.write_bytes("k", b"old")
    backend.write_bytes("k", b"new")
    assert backend.read_bytes("k") == b"new"


def test_read_missing_raises_file_not_found(backend: FsspecBackend) -> None:
    with pytest.raises(FileNotFoundError):
        backend.read_bytes("missing")


def test_open_read(backend: FsspecBackend) -> None:
    backend.write_bytes("k", b"streamed")
    with backend.open_read("k") as stream:
        assert stream.read() == b"streamed"


def test_delete(backend: FsspecBackend) -> None:
    backend.write_bytes("k", b"x")
    backend.delete("k")
    assert not backend.exists("k")


def test_delete_missing_is_noop(backend: FsspecBackend) -> None:
    backend.delete("never/written")


def test_exists(backend: FsspecBackend) -> None:
    assert not backend.exists("k")
    backend.write_bytes("k", b"x")
    assert backend.exists("k")


def test_list_prefix_recursive(backend: FsspecBackend) -> None:
    backend.write_bytes("a/b/c.txt", b"")
    backend.write_bytes("a/b/d.txt", b"")
    backend.write_bytes("a/e.txt", b"")
    backend.write_bytes("z.txt", b"")
    assert sorted(backend.list_prefix("a/")) == ["a/b/c.txt", "a/b/d.txt", "a/e.txt"]


def test_list_prefix_empty_prefix(backend: FsspecBackend) -> None:
    backend.write_bytes("a.txt", b"")
    backend.write_bytes("b/c.txt", b"")
    assert sorted(backend.list_prefix("")) == ["a.txt", "b/c.txt"]


def test_list_prefix_when_root_missing() -> None:
    fs = fsspec.filesystem("memory")
    if isinstance(fs, MemoryFileSystem):
        fs.store.clear()
        fs.pseudo_dirs.clear()
    b = FsspecBackend(fs, root="/never-created-edelrep")
    assert list(b.list_prefix("")) == []


def test_satisfies_protocol() -> None:
    fs = fsspec.filesystem("memory")
    backend: StorageBackend = FsspecBackend(fs, root="/proto-check")
    assert isinstance(backend, StorageBackend)
