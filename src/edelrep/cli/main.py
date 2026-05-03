import argparse
import sys
import threading
from pathlib import Path

from edelrep.application.reindex import ReindexUseCase
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.index.connection import open_index_database
from edelrep.infrastructure.index.projector import SqliteIndexProjector
from edelrep.infrastructure.storage import LocalFilesystemBackend
from edelrep.infrastructure.watcher.live_index import LiveIndex


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="edelrep")
    sub = parser.add_subparsers(dest="command")

    reindex = sub.add_parser("reindex", help="Rebuild the SQLite index from filesystem")
    reindex.add_argument(
        "--storage-root",
        type=Path,
        required=True,
        help="Root directory of the storage layout",
    )
    reindex.add_argument(
        "--index-path",
        type=Path,
        required=True,
        help="Path to the SQLite index file",
    )

    watch = sub.add_parser("watch", help="Run the live filesystem watcher (Ctrl-C to stop)")
    watch.add_argument(
        "--storage-root",
        type=Path,
        required=True,
        help="Root directory of the storage layout",
    )
    watch.add_argument(
        "--index-path",
        type=Path,
        required=True,
        help="Path to the SQLite index file",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 2

    if args.command == "reindex":
        return _cmd_reindex(args.storage_root, args.index_path)

    if args.command == "watch":
        return _cmd_watch(args.storage_root, args.index_path)

    parser.error(f"unknown command: {args.command}")  # pragma: no cover - argparse rejects first
    return 2  # pragma: no cover - parser.error raises SystemExit


def _cmd_reindex(storage_root: Path, index_path: Path) -> int:
    storage_root.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    backend = LocalFilesystemBackend(storage_root)
    vrepo = FilesystemVehicleRepository(backend)
    rrepo = FilesystemRepairRepository(backend)
    irepo = FilesystemImageRepository(backend)

    conn = open_index_database(index_path)
    try:
        projector = SqliteIndexProjector(conn)
        use_case = ReindexUseCase(projector, vrepo, rrepo, irepo)
        stats = use_case.execute()
    finally:
        conn.close()

    line = (
        f"reindex complete: vehicles_indexed={stats.vehicles_indexed}"
        f" repairs_indexed={stats.repairs_indexed}"
        f" images_indexed={stats.images_indexed}"
        f" duration={stats.duration_seconds:.3f}s\n"
    )
    sys.stdout.write(line)
    return 0


def _cmd_watch(
    storage_root: Path,
    index_path: Path,
    *,
    stop_event: threading.Event | None = None,
) -> int:
    storage_root.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    backend = LocalFilesystemBackend(storage_root)
    vrepo = FilesystemVehicleRepository(backend)
    rrepo = FilesystemRepairRepository(backend)
    irepo = FilesystemImageRepository(backend)
    conn = open_index_database(index_path)

    projector = SqliteIndexProjector(conn)
    live = LiveIndex(storage_root, projector, vrepo, rrepo, irepo)

    live.start()
    if live.drift_detected:
        sys.stdout.write("warning: index is drifted; consider running `edelrep reindex` first\n")
    sys.stdout.write(f"watching {storage_root} (index at {index_path}); Ctrl-C to stop\n")
    sys.stdout.flush()

    event = stop_event if stop_event is not None else threading.Event()
    try:
        event.wait()
    except KeyboardInterrupt:  # pragma: no cover - SIGINT cannot be reliably tested
        pass
    finally:
        live.stop()
        conn.close()
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
