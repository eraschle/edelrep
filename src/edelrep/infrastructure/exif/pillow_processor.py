import io
from datetime import UTC, datetime

from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError

from edelrep.application.upload_image import ProcessedImage

__all__ = ["PillowImageProcessor", "ProcessedImage"]

_THUMBNAIL_MAX_SIZE = (256, 256)
_JPEG_QUALITY = 95
_THUMB_QUALITY = 85
_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"

_MIME_BY_PIL_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}


class PillowImageProcessor:
    """Pillow-backed implementation of the application ImageProcessor port.

    - Applies EXIF orientation transpose so stored pixels are upright.
    - Generates a max-256x256 aspect-preserved thumbnail (JPEG quality 85).
    - Extracts ``DateTimeOriginal`` and treats it as UTC (V1 single-workshop
      assumption per PLAN.md §2).
    """

    def process(self, raw_bytes: bytes) -> ProcessedImage:
        try:
            with Image.open(io.BytesIO(raw_bytes)) as src:
                src.load()
                fmt = (src.format or "JPEG").upper()
                captured_at = _extract_capture_time(src)
                rotated = ImageOps.exif_transpose(src)
                if rotated is None:
                    rotated = src.copy()
                rotated_bytes = _encode(rotated, fmt, _JPEG_QUALITY)
                thumb = rotated.copy()
                thumb.thumbnail(_THUMBNAIL_MAX_SIZE)
                thumbnail_bytes = _encode(thumb, fmt, _THUMB_QUALITY)
        except UnidentifiedImageError as exc:
            raise ValueError(f"input is not a recognised image: {exc}") from exc
        return ProcessedImage(
            rotated_bytes=rotated_bytes,
            thumbnail_bytes=thumbnail_bytes,
            captured_at=captured_at,
            mime_type=_MIME_BY_PIL_FORMAT.get(fmt, "application/octet-stream"),
        )


def _encode(img: Image.Image, fmt: str, quality: int) -> bytes:
    out = io.BytesIO()
    if fmt == "JPEG" and img.mode != "RGB":
        img = img.convert("RGB")
    save_kwargs: dict[str, object] = {}
    if fmt == "JPEG":
        save_kwargs["quality"] = quality
    img.save(out, format=fmt, **save_kwargs)
    return out.getvalue()


def _extract_capture_time(img: Image.Image) -> datetime | None:
    try:
        exif = img.getexif()
    except (AttributeError, KeyError, OSError):
        return None
    if not exif:
        return None
    raw = exif.get(ExifTags.Base.DateTimeOriginal.value)
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("ascii", errors="ignore")
    try:
        naive = datetime.strptime(str(raw), _DATETIME_FORMAT)
    except ValueError:
        return None
    return naive.replace(tzinfo=UTC)
