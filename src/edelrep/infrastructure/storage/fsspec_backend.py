from collections.abc import Iterable
from typing import BinaryIO

import fsspec


class FsspecBackend:
    """StorageBackend implementation backed by any fsspec filesystem.

    The backend prepends ``root`` to every key. Atomicity is delegated to
    the underlying fsspec implementation: ``MemoryFileSystem`` writes are
    trivially atomic; remote backends honour the provider's per-object
    contract (e.g., S3 PUT is atomic at object granularity). No
    temp-file-and-rename emulation is added — most fsspec implementations
    do not support a generic rename.
    """

    def __init__(self, filesystem: fsspec.AbstractFileSystem, root: str) -> None:
        self._fs = filesystem
        self._root = root.rstrip("/")

    def _full(self, key: str) -> str:
        return f"{self._root}/{key}" if key else self._root

    def read_bytes(self, key: str) -> bytes:
        return self._fs.cat_file(self._full(key))  # type: ignore[no-any-return]

    def size(self, key: str) -> int:
        size = self._fs.size(self._full(key))
        if size is None:  # pragma: no cover - fsspec returns a size for existing files
            raise FileNotFoundError(key)
        return int(size)

    def write_bytes(self, key: str, data: bytes) -> None:
        self._fs.pipe_file(self._full(key), data)

    def open_read(self, key: str) -> BinaryIO:
        return self._fs.open(self._full(key), "rb")  # type: ignore[no-any-return]

    def delete(self, key: str) -> None:
        full = self._full(key)
        if self._fs.exists(full):
            self._fs.rm_file(full)

    def exists(self, key: str) -> bool:
        return bool(self._fs.exists(self._full(key)))

    def list_prefix(self, prefix: str) -> Iterable[str]:
        base = self._full(prefix) if prefix else self._root
        if not self._fs.exists(base):
            return
        try:
            entries = self._fs.find(base)
        except FileNotFoundError:
            return
        for entry in sorted(entries):
            if entry == self._root or entry == self._root + "/":
                continue
            relative = entry[len(self._root) + 1 :] if entry.startswith(self._root + "/") else entry
            yield relative
