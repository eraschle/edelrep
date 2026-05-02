from collections.abc import Iterable
from typing import BinaryIO, Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Low-level byte-stream and path operations for the storage root.

    Implementations may target the local filesystem, S3, WebDAV, etc.
    All paths are POSIX-style strings relative to a storage root.
    """

    def read_bytes(self, key: str) -> bytes:
        """Return the full contents of ``key``. Raises ``FileNotFoundError``."""
        ...

    def write_bytes(self, key: str, data: bytes) -> None:
        """Atomically write ``data`` to ``key``, creating parent dirs as needed."""
        ...

    def open_read(self, key: str) -> BinaryIO:
        """Open ``key`` for streaming reads. Caller closes the returned object."""
        ...

    def delete(self, key: str) -> None:
        """Delete ``key``. No-op if missing."""
        ...

    def exists(self, key: str) -> bool:
        """Return whether ``key`` is present."""
        ...

    def list_prefix(self, prefix: str) -> Iterable[str]:
        """Iterate keys whose path starts with ``prefix``."""
        ...
