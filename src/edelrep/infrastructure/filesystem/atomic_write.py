import os
from pathlib import Path


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Atomically write ``data`` to ``path``.

    Creates parent directories as needed. Uses a same-directory temp file
    plus :func:`os.replace` so a reader either sees the old content or the
    new content, never a partial write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = os.urandom(4).hex()
    tmp = path.with_name(f"{path.name}.tmp.{suffix}")
    try:
        with tmp.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    except BaseException:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def write_text_atomic(path: Path, text: str, encoding: str = "utf-8") -> None:
    write_bytes_atomic(path, text.encode(encoding))
