import mimetypes
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from ulid import ULID

from edelrep.domain.entities import Image, ImageSource
from edelrep.domain.exceptions import ImageNotFound, RepairNotFound
from edelrep.infrastructure.filesystem.atomic_write import write_bytes_atomic
from edelrep.infrastructure.filesystem.layout import REPAIR_DIR_NAME_RE, image_filename, thumbnail_path
from edelrep.infrastructure.filesystem.sidecar import read_sidecar

_IMAGE_FILE_RE = re.compile(r"^(\d{4})_([0-9A-HJKMNP-TV-Z]{26})\.([a-zA-Z0-9]+)$")


class FilesystemImageRepository:
    """ImageRepository implementation that stores raw bytes plus optional thumbnails.

    Phase 2 read-time defaults (documented in PLAN.md §6 / plan §Design Notes):
    - source is always ImageSource.MANUAL on read; the EMAIL distinction
      requires Phase 8 inbox correlation.
    - captured_at is always None on read; EXIF parsing arrives in Phase 4.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def get(self, image_id: ULID) -> Image:
        for image_path, repair_id in self._iter_image_files():
            match = _IMAGE_FILE_RE.match(image_path.name)
            if match and ULID.from_str(match.group(2)) == image_id:
                return self._reconstruct(image_path, repair_id)
        raise ImageNotFound(image_id)

    def save(
        self,
        image: Image,
        *,
        raw_bytes: bytes,
        thumbnail_bytes: bytes | None = None,
    ) -> None:
        repair_dir = self._find_repair_dir(image.repair_id)
        if repair_dir is None:
            raise RepairNotFound(image.repair_id)
        existing = sum(1 for p in repair_dir.iterdir() if p.is_file() and _IMAGE_FILE_RE.match(p.name))
        seq = existing + 1
        parts = image.filename.rsplit(".", 1)
        extension = (parts[1] if len(parts) == 2 and parts[1] else "bin").lower()
        name = image_filename(seq=seq, image_id=image.id, extension=extension)
        write_bytes_atomic(repair_dir / name, raw_bytes)
        if thumbnail_bytes is not None:
            write_bytes_atomic(thumbnail_path(repair_dir, name), thumbnail_bytes)

    def list_for_repair(self, repair_id: ULID) -> Iterable[Image]:
        repair_dir = self._find_repair_dir(repair_id)
        if repair_dir is None:
            return
        files = sorted(p for p in repair_dir.iterdir() if p.is_file() and _IMAGE_FILE_RE.match(p.name))
        for path in files:
            yield self._reconstruct(path, repair_id)

    def _find_repair_dir(self, repair_id: ULID) -> Path | None:
        if not self._root.is_dir():
            return None
        for vdir in self._root.iterdir():
            if not vdir.is_dir() or vdir.name.startswith("_"):
                continue
            for rdir in vdir.iterdir():
                if not rdir.is_dir() or not REPAIR_DIR_NAME_RE.match(rdir.name):
                    continue
                sidecar = rdir / "_repair.json"
                if not sidecar.is_file():
                    continue
                data = read_sidecar(sidecar)
                if str(data.get("id")) == str(repair_id):
                    return rdir
        return None

    def _iter_image_files(self) -> Iterable[tuple[Path, ULID]]:
        if not self._root.is_dir():
            return
        for vdir in self._root.iterdir():
            if not vdir.is_dir() or vdir.name.startswith("_"):
                continue
            for rdir in vdir.iterdir():
                if not rdir.is_dir() or not REPAIR_DIR_NAME_RE.match(rdir.name):
                    continue
                sidecar = rdir / "_repair.json"
                if not sidecar.is_file():
                    continue
                data = read_sidecar(sidecar)
                rid = ULID.from_str(str(data["id"]))
                for entry in rdir.iterdir():
                    if entry.is_file() and _IMAGE_FILE_RE.match(entry.name):
                        yield entry, rid

    def _reconstruct(self, path: Path, repair_id: ULID) -> Image:
        match = _IMAGE_FILE_RE.match(path.name)
        if match is None:
            raise ValueError(f"unexpected image filename: {path.name!r}")
        image_id = ULID.from_str(match.group(2))
        thumb = path.parent / "_thumbs" / path.name
        rel_storage = path.relative_to(self._root).as_posix()
        rel_thumb = thumb.relative_to(self._root).as_posix() if thumb.is_file() else None
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        stat = path.stat()
        return Image(
            id=image_id,
            repair_id=repair_id,
            storage_key=rel_storage,
            thumbnail_key=rel_thumb,
            filename=path.name,
            mime_type=mime,
            size_bytes=stat.st_size,
            source=ImageSource.MANUAL,
            uploaded_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            captured_at=None,
        )
