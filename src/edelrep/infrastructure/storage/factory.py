from pathlib import Path
from typing import Any

import fsspec

from edelrep.domain.ports import StorageBackend
from edelrep.infrastructure.storage.fsspec_backend import FsspecBackend
from edelrep.infrastructure.storage.local_filesystem import LocalFilesystemBackend


def build_storage_backend(config: dict[str, Any]) -> StorageBackend:
    """Construct a StorageBackend from a config dict.

    Schema:

    .. code-block:: toml

       [storage]
       mode = "local" | "fsspec"
       root = "..."           # required for "local"

       [storage.fsspec]       # required for "fsspec"
       protocol = "..."
       root = "..."
       options = { ... }
    """
    mode = config.get("mode")
    if mode == "local":
        root = config.get("root")
        if not root:
            raise ValueError("storage.mode=local requires 'root'")
        path = Path(root)
        path.mkdir(parents=True, exist_ok=True)
        return LocalFilesystemBackend(path)
    if mode == "fsspec":
        fs_cfg = config.get("fsspec") or {}
        protocol = fs_cfg.get("protocol")
        if not protocol:
            raise ValueError("storage.mode=fsspec requires fsspec.protocol")
        root = fs_cfg.get("root")
        if not root:
            raise ValueError("storage.mode=fsspec requires fsspec.root")
        options = fs_cfg.get("options") or {}
        try:
            fs = fsspec.filesystem(protocol, **options)
        except ValueError as exc:
            raise ValueError(f"storage.mode=fsspec: {exc}") from exc
        return FsspecBackend(fs, root=root)
    raise ValueError(f"unknown storage mode: {mode!r}")
