"""Einmaliger Helper: Logo + Favicon von edelmannmotos.ch laden, Logo
mit transparentem Hintergrund als PNG speichern.

Output:
    src/edelrep/presentation/static/edelmann-logo.png
    src/edelrep/presentation/static/favicon.ico

Re-run nach Marken-Update auf der Edelmann-Site — Output wird ins Repo
committed, kein Runtime-Netzwerk.
"""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path

from PIL import Image

LOGO_URL = "https://files.designer.hoststar.ch/96/58/9658be91-e409-491c-8729-a8db54dcbe42.jpg"
FAVICON_URL = "https://files.designer.hoststar.ch/4d/12/4d12297c-e063-4950-80cd-49dab8c26b4a.ico"

STATIC_DIR = Path(__file__).resolve().parent.parent / "src" / "edelrep" / "presentation" / "static"
LOGO_OUT = STATIC_DIR / "edelmann-logo.png"
FAVICON_OUT = STATIC_DIR / "favicon.ico"

WHITE_THRESHOLD = 240  # Pixel mit r,g,b alle >= 240 -> alpha=0


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 edelrep-branding-script"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def make_logo_transparent(raw: bytes) -> bytes:
    """Open the raw image bytes, mask near-white pixels to alpha=0, return PNG bytes."""
    src = Image.open(io.BytesIO(raw)).convert("RGBA")
    masked: list[tuple[int, int, int, int]] = []
    for r, g, b, a in src.getdata():  # type: ignore[misc]
        if r >= WHITE_THRESHOLD and g >= WHITE_THRESHOLD and b >= WHITE_THRESHOLD:
            masked.append((r, g, b, 0))
        else:
            masked.append((r, g, b, a))
    out = Image.new("RGBA", src.size)
    out.putdata(masked)
    buffer = io.BytesIO()
    out.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def main() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading logo from {LOGO_URL}")
    raw_logo = _fetch(LOGO_URL)
    print(f"  raw {len(raw_logo)} bytes")
    transparent_png = make_logo_transparent(raw_logo)
    LOGO_OUT.write_bytes(transparent_png)
    with Image.open(LOGO_OUT) as written:
        size = written.size
    print(f"  saved {LOGO_OUT} ({len(transparent_png)} bytes, {size[0]}x{size[1]})")

    print(f"Downloading favicon from {FAVICON_URL}")
    favicon = _fetch(FAVICON_URL)
    FAVICON_OUT.write_bytes(favicon)
    print(f"  saved {FAVICON_OUT} ({len(favicon)} bytes)")


if __name__ == "__main__":
    main()
