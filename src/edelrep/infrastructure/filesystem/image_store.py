import mimetypes
import re
from collections.abc import Iterable
from datetime import UTC, datetime

from ulid import ULID

from edelrep.domain.entities import Image, ImageSource
from edelrep.domain.exceptions import ImageNotFound, RepairNotFound
from edelrep.domain.ports import StorageBackend
from edelrep.infrastructure.filesystem.layout import (
    image_filename,
    image_key,
    image_sidecar_key,
    is_image_key,
    is_repair_sidecar_key,
    thumbnail_key,
)
from edelrep.infrastructure.filesystem.sidecar import (
    read_backend_sidecar,
    write_backend_sidecar,
)

_IMAGE_FILE_RE = re.compile(r"^(\d{4})_([0-9A-HJKMNP-TV-Z]{26})\.([a-zA-Z0-9]+)$")


class FilesystemImageRepository:
    """ImageRepository implementation against any StorageBackend.

    Per-image sidecar: ``<vehicle_ulid>/<repair-dir>/NNNN_<ulid>.json``
    carries optional fields like ``comment``. Absence = no comment.
    """

    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend

    def get(self, image_id: ULID) -> Image:
        for key in self._backend.list_prefix(""):
            if not is_image_key(key):
                continue
            filename = key.rsplit("/", 1)[1]
            match = _IMAGE_FILE_RE.match(filename)
            if match and ULID.from_str(match.group(2)) == image_id:
                repair_id = self._repair_id_for_image_key(key)
                return self._reconstruct(key, repair_id)
        raise ImageNotFound(image_id)

    def save(
        self,
        image: Image,
        *,
        raw_bytes: bytes,
        thumbnail_bytes: bytes | None = None,
    ) -> None:
        repair_path = self._find_repair_path(image.repair_id)
        if repair_path is None:
            raise RepairNotFound(image.repair_id)
        vehicle_str, dir_name = repair_path
        prefix = f"{vehicle_str}/{dir_name}/"
        existing = sum(1 for k in self._backend.list_prefix(prefix) if is_image_key(k))
        seq = existing + 1
        parts = image.filename.rsplit(".", 1)
        extension = (parts[1] if len(parts) == 2 and parts[1] else "bin").lower()
        vehicle_id = ULID.from_str(vehicle_str)
        name = image_filename(seq=seq, image_id=image.id, extension=extension)
        self._backend.write_bytes(image_key(vehicle_id, dir_name, name), raw_bytes)
        if thumbnail_bytes is not None:
            self._backend.write_bytes(thumbnail_key(vehicle_id, dir_name, name), thumbnail_bytes)
        if image.comment is not None:
            write_backend_sidecar(
                self._backend,
                image_sidecar_key(vehicle_id, dir_name, name),
                {"comment": image.comment},
            )

    def list_for_repair(self, repair_id: ULID) -> Iterable[Image]:
        repair_path = self._find_repair_path(repair_id)
        if repair_path is None:
            return
        vehicle_str, dir_name = repair_path
        prefix = f"{vehicle_str}/{dir_name}/"
        keys = sorted(k for k in self._backend.list_prefix(prefix) if is_image_key(k))
        for key in keys:
            yield self._reconstruct(key, repair_id)

    def update_comment(self, image_id: ULID, comment: str | None) -> None:
        for key in self._backend.list_prefix(""):
            if not is_image_key(key):
                continue
            filename = key.rsplit("/", 1)[1]
            match = _IMAGE_FILE_RE.match(filename)
            if match and ULID.from_str(match.group(2)) == image_id:
                vehicle_str, dir_name, name = key.split("/", 2)
                vehicle_id = ULID.from_str(vehicle_str)
                sidecar = image_sidecar_key(vehicle_id, dir_name, name)
                if comment is None:
                    if self._backend.exists(sidecar):
                        self._backend.delete(sidecar)
                else:
                    write_backend_sidecar(self._backend, sidecar, {"comment": comment})
                return
        raise ImageNotFound(image_id)

    def _find_repair_path(self, repair_id: ULID) -> tuple[str, str] | None:
        for key in self._backend.list_prefix(""):
            if not is_repair_sidecar_key(key):
                continue
            data = read_backend_sidecar(self._backend, key)
            if str(data.get("id")) == str(repair_id):
                vehicle_str, dir_name, _ = key.split("/", 2)
                return vehicle_str, dir_name
        return None

    def _repair_id_for_image_key(self, key: str) -> ULID:
        vehicle_str, dir_name, _ = key.split("/", 2)
        sidecar = f"{vehicle_str}/{dir_name}/_repair.json"
        data = read_backend_sidecar(self._backend, sidecar)
        return ULID.from_str(str(data["id"]))

    def _reconstruct(self, key: str, repair_id: ULID) -> Image:
        filename = key.rsplit("/", 1)[1]
        match = _IMAGE_FILE_RE.match(filename)
        if match is None:  # pragma: no cover - callers pre-filter on is_image_key
            raise ValueError(f"unexpected image filename: {filename!r}")
        image_id = ULID.from_str(match.group(2))
        thumb_candidate = key.rsplit("/", 1)[0] + "/_thumbs/" + filename
        raw = self._backend.read_bytes(key)
        thumb_key_value = thumb_candidate if self._backend.exists(thumb_candidate) else None
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        vehicle_str, dir_name, _ = key.split("/", 2)
        sidecar = image_sidecar_key(ULID.from_str(vehicle_str), dir_name, filename)
        comment: str | None = None
        if self._backend.exists(sidecar):
            data = read_backend_sidecar(self._backend, sidecar)
            raw_comment = data.get("comment")
            if isinstance(raw_comment, str):
                comment = raw_comment

        return Image(
            id=image_id,
            repair_id=repair_id,
            storage_key=key,
            thumbnail_key=thumb_key_value,
            filename=filename,
            mime_type=mime,
            size_bytes=len(raw),
            source=ImageSource.MANUAL,
            uploaded_at=datetime.now(UTC),
            captured_at=None,
            comment=comment,
        )
