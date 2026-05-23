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

    serve = sub.add_parser("serve", help="Run the edelrep web UI (Ctrl-C to stop)")
    serve.add_argument(
        "--storage-root",
        type=Path,
        required=True,
        help="Root directory of the storage layout",
    )
    serve.add_argument(
        "--index-path",
        type=Path,
        required=True,
        help="Path to the SQLite index file",
    )
    serve.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1)",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind (default: 8080)",
    )
    serve.add_argument(
        "--email-config",
        type=Path,
        default=None,
        help="Path to TOML file with [email] section enabling IMAP poller",
    )

    cleanup = sub.add_parser(
        "cleanup",
        help="Hard-delete soft-deleted vehicles older than the retention window",
    )
    cleanup.add_argument(
        "--storage-root",
        type=Path,
        required=True,
        help="Root directory of the storage layout",
    )
    cleanup.add_argument(
        "--index-path",
        type=Path,
        required=True,
        help="Path to the SQLite index file",
    )
    cleanup.add_argument(
        "--older-than-days",
        type=int,
        default=30,
        help="Retention window in days (default: 30)",
    )

    migrate = sub.add_parser("migrate-storage", help="Copy storage tree to a new location and verify counts")
    migrate.add_argument(
        "--from",
        dest="source_root",
        type=Path,
        required=True,
        help="Source storage root",
    )
    migrate.add_argument(
        "--to",
        dest="target_root",
        type=Path,
        required=True,
        help="Target storage root (must not exist or be empty)",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 2

    if args.command == "reindex":
        return _cmd_reindex(args.storage_root, args.index_path)

    if args.command == "watch":
        return _cmd_watch(args.storage_root, args.index_path)

    if args.command == "serve":
        return _cmd_serve(
            args.storage_root,
            args.index_path,
            args.host,
            args.port,
            args.email_config,
        )

    if args.command == "cleanup":
        return _cmd_cleanup(args.storage_root, args.index_path, args.older_than_days)

    if args.command == "migrate-storage":
        return _cmd_migrate_storage(args.source_root, args.target_root)

    parser.error(f"unknown command: {args.command}")  # pragma: no cover - argparse rejects first
    return 2  # pragma: no cover - parser.error raises SystemExit


def _cmd_reindex(storage_root: Path, index_path: Path) -> int:
    storage_root.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    backend = LocalFilesystemBackend(storage_root)
    vrepo = FilesystemVehicleRepository(backend)
    rrepo = FilesystemRepairRepository(backend)
    irepo = FilesystemImageRepository(backend)

    conn, lock = open_index_database(index_path)
    try:
        projector = SqliteIndexProjector(conn, lock)
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
    conn, lock = open_index_database(index_path)

    projector = SqliteIndexProjector(conn, lock)
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


def _cmd_serve(
    storage_root: Path,
    index_path: Path,
    host: str,
    port: int,
    email_config_path: Path | None = None,
) -> int:  # pragma: no cover - uvicorn.run blocks indefinitely
    import uvicorn  # noqa: PLC0415

    from edelrep.infrastructure.email.config import load_email_config  # noqa: PLC0415
    from edelrep.presentation.app_factory import create_app  # noqa: PLC0415
    from edelrep.presentation.container import build_container  # noqa: PLC0415

    storage_root.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    email_config = load_email_config(email_config_path) if email_config_path else None
    container = build_container(
        storage_root,
        index_path,
        with_live_index=True,
        email_config=email_config,
    )
    app = create_app(container)
    uvicorn.run(app, host=host, port=port)
    return 0


def _cmd_cleanup(storage_root: Path, index_path: Path, older_than_days: int) -> int:
    from edelrep.application.delete_vehicle import CleanupDeletedVehiclesUseCase  # noqa: PLC0415
    from edelrep.infrastructure.index.sqlite_search_index import SqliteSearchIndex  # noqa: PLC0415

    storage_root.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    backend = LocalFilesystemBackend(storage_root)
    vrepo = FilesystemVehicleRepository(backend)
    conn, lock = open_index_database(index_path)
    try:
        search_index = SqliteSearchIndex(conn, lock)
        use_case = CleanupDeletedVehiclesUseCase(vrepo, search_index)
        stats = use_case.execute(retention_days=older_than_days)
    finally:
        conn.close()

    sys.stdout.write(
        f"cleanup complete: vehicles_purged={stats.vehicles_purged} "
        f"older_than_days={older_than_days}\n"
    )
    return 0


def _cmd_migrate_storage(source_root: Path, target_root: Path) -> int:
    from edelrep.application.migrate_storage import MigrateStorageUseCase  # noqa: PLC0415

    try:
        stats = MigrateStorageUseCase().execute(
            source_root=source_root,
            target_root=target_root,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    sys.stdout.write(
        f"migration complete: files_copied={stats.files_copied} "
        f"bytes_copied={stats.bytes_copied} duration={stats.duration_seconds:.3f}s\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
