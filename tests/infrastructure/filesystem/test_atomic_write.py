import os
from pathlib import Path

import pytest

from edelrep.infrastructure.filesystem.atomic_write import (
    write_bytes_atomic,
    write_text_atomic,
)


def test_write_bytes_atomic_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"
    write_bytes_atomic(target, b"hello")
    assert target.read_bytes() == b"hello"


def test_write_bytes_atomic_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c" / "out.bin"
    write_bytes_atomic(target, b"x")
    assert target.read_bytes() == b"x"


def test_write_bytes_atomic_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"
    target.write_bytes(b"old")
    write_bytes_atomic(target, b"new")
    assert target.read_bytes() == b"new"


def test_write_bytes_atomic_no_partial_on_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "out.bin"
    target.write_bytes(b"original")

    def boom(self: Path, _dst: str | os.PathLike[str]) -> Path:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(Path, "replace", boom)

    with pytest.raises(OSError, match="simulated rename failure"):
        write_bytes_atomic(target, b"new content")

    assert target.read_bytes() == b"original"
    assert not list(tmp_path.glob("*.tmp.*"))


def test_write_text_atomic_round_trips_unicode(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    write_text_atomic(target, "Schöne Grüße — Ümläüte")
    assert target.read_text(encoding="utf-8") == "Schöne Grüße — Ümläüte"


def test_write_text_atomic_uses_utf8_by_default(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    write_text_atomic(target, "Ä")
    assert target.read_bytes() == b"\xc3\x84"
