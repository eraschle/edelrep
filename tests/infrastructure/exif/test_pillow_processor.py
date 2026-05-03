import io
from datetime import UTC, datetime

import pytest
from PIL import ExifTags, Image, ImageOps

from edelrep.infrastructure.exif.pillow_processor import (
    PillowImageProcessor,
    ProcessedImage,
)


def _make_jpeg_bytes(
    *,
    size: tuple[int, int] = (640, 480),
    orientation: int = 1,
    capture_time: str | None = None,
) -> bytes:
    img = Image.new("RGB", size, color=(123, 200, 50))
    exif = img.getexif()
    if orientation != 1:
        exif[ExifTags.Base.Orientation.value] = orientation
    if capture_time is not None:
        exif[ExifTags.Base.DateTimeOriginal.value] = capture_time
        exif[ExifTags.Base.DateTime.value] = capture_time
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif, quality=95)
    return buf.getvalue()


def test_process_returns_rotated_and_thumbnail_bytes() -> None:
    raw = _make_jpeg_bytes(size=(800, 600))
    processor = PillowImageProcessor()
    result = processor.process(raw)

    assert isinstance(result, ProcessedImage)
    assert len(result.rotated_bytes) > 0
    assert len(result.thumbnail_bytes) > 0
    assert result.thumbnail_bytes != result.rotated_bytes


def test_thumbnail_fits_within_max_dimensions() -> None:
    raw = _make_jpeg_bytes(size=(2000, 1500))
    processor = PillowImageProcessor()
    result = processor.process(raw)

    with Image.open(io.BytesIO(result.thumbnail_bytes)) as thumb:
        assert thumb.width <= 256
        assert thumb.height <= 256


def test_thumbnail_preserves_aspect_ratio() -> None:
    raw = _make_jpeg_bytes(size=(2000, 1000))  # 2:1
    processor = PillowImageProcessor()
    result = processor.process(raw)

    with Image.open(io.BytesIO(result.thumbnail_bytes)) as thumb:
        # 2:1 source → 256x128 thumbnail
        assert thumb.width == 256
        assert thumb.height == 128


def test_process_extracts_capture_time_as_utc() -> None:
    raw = _make_jpeg_bytes(capture_time="2026:05:03 14:30:00")
    processor = PillowImageProcessor()
    result = processor.process(raw)

    assert result.captured_at == datetime(2026, 5, 3, 14, 30, 0, tzinfo=UTC)


def test_process_returns_none_capture_time_when_absent() -> None:
    raw = _make_jpeg_bytes()
    processor = PillowImageProcessor()
    result = processor.process(raw)

    assert result.captured_at is None


def test_process_returns_none_capture_time_when_unparseable() -> None:
    raw = _make_jpeg_bytes(capture_time="not-a-date")
    processor = PillowImageProcessor()
    result = processor.process(raw)

    assert result.captured_at is None


def test_rotated_bytes_strip_orientation_tag() -> None:
    raw = _make_jpeg_bytes(size=(640, 480), orientation=6)
    processor = PillowImageProcessor()
    result = processor.process(raw)

    with Image.open(io.BytesIO(result.rotated_bytes)) as rotated:
        exif = rotated.getexif()
        orientation = exif.get(ExifTags.Base.Orientation.value, 1)
        assert orientation == 1
        # Width/height swapped due to 90° rotation
        assert rotated.width == 480
        assert rotated.height == 640


def test_mime_type_is_image_jpeg_for_jpeg_input() -> None:
    raw = _make_jpeg_bytes()
    processor = PillowImageProcessor()
    result = processor.process(raw)
    assert result.mime_type == "image/jpeg"


def test_process_rejects_non_image_bytes() -> None:
    processor = PillowImageProcessor()
    with pytest.raises(ValueError, match="image"):
        processor.process(b"not an image at all")


def test_process_handles_exif_transpose_returning_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _make_jpeg_bytes()
    monkeypatch.setattr(ImageOps, "exif_transpose", lambda img: None)
    processor = PillowImageProcessor()
    result = processor.process(raw)
    assert len(result.rotated_bytes) > 0
    # Falls through to src.copy() — no rotation applied.


def test_process_decodes_bytes_capture_time(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = _make_jpeg_bytes(capture_time="2026:05:03 14:30:00")
    real_get = Image.Exif.get

    def get_as_bytes(self, key, default=None):
        value = real_get(self, key, default)
        if key == ExifTags.Base.DateTimeOriginal.value and isinstance(value, str):
            return value.encode("ascii")
        return value

    monkeypatch.setattr(Image.Exif, "get", get_as_bytes)
    processor = PillowImageProcessor()
    result = processor.process(raw)
    assert result.captured_at == datetime(2026, 5, 3, 14, 30, 0, tzinfo=UTC)
