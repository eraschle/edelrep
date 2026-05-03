import shutil
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MigrationStats:
    files_copied: int
    bytes_copied: int
    duration_seconds: float


class MigrateStorageUseCase:
    """Copy storage tree from one local root to another using shutil.copytree.

    Verifies the file count matches post-copy. Refuses to overwrite a non-empty
    target. Local-FS only — fsspec migration is out of scope for V1.
    """

    def execute(
        self,
        *,
        source_root: Path,
        target_root: Path,
    ) -> MigrationStats:
        if not source_root.is_dir():
            raise FileNotFoundError(f"source root does not exist: {source_root}")
        if target_root.exists():
            if any(target_root.iterdir()):
                raise ValueError(f"target root is not empty: {target_root}; refusing to overwrite")
            target_root.rmdir()  # let copytree create it fresh

        start = time.perf_counter()
        shutil.copytree(source_root, target_root)
        duration = time.perf_counter() - start

        source_files = sorted(p for p in source_root.rglob("*") if p.is_file())
        target_files = sorted(p for p in target_root.rglob("*") if p.is_file())
        if len(source_files) != len(target_files):
            raise RuntimeError(
                f"verification failed: source has {len(source_files)} files, target has {len(target_files)}"
            )

        bytes_copied = sum(f.stat().st_size for f in target_files)
        return MigrationStats(
            files_copied=len(target_files),
            bytes_copied=bytes_copied,
            duration_seconds=duration,
        )
