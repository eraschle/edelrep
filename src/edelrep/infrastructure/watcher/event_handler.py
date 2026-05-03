from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.events import FileMovedEvent, FileSystemEvent, FileSystemEventHandler

from edelrep.infrastructure.watcher.key_mapper import (
    EntityKind,
    classify,
    is_temp_atomic_write,
    path_to_key,
)

if TYPE_CHECKING:
    from edelrep.infrastructure.watcher.debouncer import Debouncer


_IGNORED_KINDS = {EntityKind.IGNORED, EntityKind.THUMBNAIL}


class KeyEventHandler(FileSystemEventHandler):
    """Maps watchdog events to storage keys and feeds the debouncer."""

    def __init__(self, storage_root: Path, debouncer: "Debouncer") -> None:
        self._storage_root = storage_root
        self._debouncer = debouncer

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        paths: list[str] = [str(event.src_path)]
        if isinstance(event, FileMovedEvent):
            paths.append(str(event.dest_path))
        for raw in paths:
            path = Path(raw)
            if is_temp_atomic_write(path):
                continue
            key = path_to_key(path, self._storage_root)
            if key is None:
                continue
            if classify(key) in _IGNORED_KINDS:
                continue
            self._debouncer.add(key)
