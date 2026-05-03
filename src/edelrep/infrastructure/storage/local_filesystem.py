from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO

from edelrep.infrastructure.filesystem.atomic_write import write_bytes_atomic


class LocalFilesystemBackend:
    """StorageBackend implementation against the local filesystem.

    All keys are POSIX-style strings rooted at the configured directory.
    Writes are atomic via tempfile + replace (see ``atomic_write`` module).
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def _path(self, key: str) -> Path:
        if not key:
            return self._root
        candidate = self._root.joinpath(*key.split("/"))
        # Refuse anything that escapes the root (resolves ".." segments etc).
        root_resolved = self._root.resolve()
        try:
            resolved = candidate.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise ValueError(f"key {key!r} cannot be resolved under storage root") from exc
        if resolved != root_resolved and not resolved.is_relative_to(root_resolved):
            raise ValueError(f"key {key!r} escapes storage root")
        # Return the unresolved path so symlinks / non-existent parents work normally.
        return candidate

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def write_bytes(self, key: str, data: bytes) -> None:
        write_bytes_atomic(self._path(key), data)

    def open_read(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list_prefix(self, prefix: str) -> Iterable[str]:
        if not self._root.is_dir():
            return
        base = self._path(prefix) if prefix else self._root
        if prefix and not base.exists():
            return
        target = base if prefix and base.is_dir() else self._root
        prefix_check = prefix if prefix.endswith("/") or prefix == "" else f"{prefix}/"
        for path in sorted(target.rglob("*")):
            if not path.is_file():
                continue
            key = path.relative_to(self._root).as_posix()
            if prefix == "" or key.startswith(prefix_check) or key == prefix:
                yield key
