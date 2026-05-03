from collections.abc import Iterable
from pathlib import Path

import pytest

from edelrep.domain.ports import StorageBackend
from edelrep.infrastructure.storage.local_filesystem import LocalFilesystemBackend


@pytest.fixture
def backend(tmp_path: Path) -> LocalFilesystemBackend:
    return LocalFilesystemBackend(tmp_path / "store")


def test_write_then_read_round_trip(backend: LocalFilesystemBackend) -> None:
    backend.write_bytes("a/b/c.txt", b"hello")
    assert backend.read_bytes("a/b/c.txt") == b"hello"


def test_write_creates_parent_dirs(backend: LocalFilesystemBackend, tmp_path: Path) -> None:
    backend.write_bytes("nested/deep/file.bin", b"x")
    assert (tmp_path / "store" / "nested" / "deep" / "file.bin").read_bytes() == b"x"


def test_write_overwrites_existing(backend: LocalFilesystemBackend) -> None:
    backend.write_bytes("k", b"old")
    backend.write_bytes("k", b"new")
    assert backend.read_bytes("k") == b"new"


def test_write_is_atomic(backend: LocalFilesystemBackend, monkeypatch: pytest.MonkeyPatch) -> None:
    backend.write_bytes("k", b"original")
    real_replace = Path.replace

    def boom(self: Path, target: str | Path) -> Path:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError, match="simulated rename failure"):
        backend.write_bytes("k", b"new")
    monkeypatch.setattr(Path, "replace", real_replace)
    assert backend.read_bytes("k") == b"original"


def test_read_missing_raises_file_not_found(backend: LocalFilesystemBackend) -> None:
    with pytest.raises(FileNotFoundError):
        backend.read_bytes("does/not/exist")


def test_open_read_streams_bytes(backend: LocalFilesystemBackend) -> None:
    backend.write_bytes("k", b"streamed")
    with backend.open_read("k") as stream:
        assert stream.read() == b"streamed"


def test_delete_removes_key(backend: LocalFilesystemBackend) -> None:
    backend.write_bytes("k", b"x")
    assert backend.exists("k")
    backend.delete("k")
    assert not backend.exists("k")


def test_delete_missing_is_noop(backend: LocalFilesystemBackend) -> None:
    backend.delete("never/written")  # no exception


def test_exists(backend: LocalFilesystemBackend) -> None:
    assert not backend.exists("k")
    backend.write_bytes("k", b"x")
    assert backend.exists("k")


def test_list_prefix_recursive(backend: LocalFilesystemBackend) -> None:
    backend.write_bytes("a/b/c.txt", b"")
    backend.write_bytes("a/b/d.txt", b"")
    backend.write_bytes("a/e.txt", b"")
    backend.write_bytes("z.txt", b"")
    assert sorted(backend.list_prefix("a/")) == ["a/b/c.txt", "a/b/d.txt", "a/e.txt"]


def test_list_prefix_empty_prefix(backend: LocalFilesystemBackend) -> None:
    backend.write_bytes("a.txt", b"")
    backend.write_bytes("b/c.txt", b"")
    assert sorted(backend.list_prefix("")) == ["a.txt", "b/c.txt"]


def test_list_prefix_returns_iterable_of_strings(backend: LocalFilesystemBackend) -> None:
    backend.write_bytes("k.txt", b"")
    result: Iterable[str] = backend.list_prefix("")
    listed = list(result)
    assert all(isinstance(k, str) for k in listed)


def test_list_prefix_when_root_missing(tmp_path: Path) -> None:
    b = LocalFilesystemBackend(tmp_path / "never_created")
    assert list(b.list_prefix("")) == []


def test_satisfies_protocol(tmp_path: Path) -> None:
    backend: StorageBackend = LocalFilesystemBackend(tmp_path)
    assert isinstance(backend, StorageBackend)


@pytest.mark.parametrize(
    "bad_key",
    [
        "../etc/passwd",
        "../../etc/passwd",
        "vehicle/../../../etc/passwd",
        "..",
    ],
)
def test_rejects_path_traversal(backend: LocalFilesystemBackend, bad_key: str) -> None:
    with pytest.raises(ValueError, match="escapes storage root"):
        backend.write_bytes(bad_key, b"x")


def test_dot_segments_within_root_allowed(backend: LocalFilesystemBackend) -> None:
    # "a/b/.." resolves to "a", which is still inside root.
    backend.write_bytes("a/b/c.txt", b"x")
    backend.write_bytes("a/b/../d.txt", b"y")
    assert backend.read_bytes("a/d.txt") == b"y"
