"""Build Windows .ico and macOS .icns files from assets/logo.png."""

from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "logo.png"
ICO = ROOT / "assets" / "logo.ico"
ICNS = ROOT / "assets" / "logo.icns"

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICNS_TYPES = (
    ("icp4", 16),
    ("icp5", 32),
    ("icp6", 64),
    ("ic07", 128),
    ("ic08", 256),
    ("ic09", 512),
    ("ic10", 1024),
    ("ic11", 32),
    ("ic12", 64),
    ("ic13", 256),
    ("ic14", 512),
)


def _png_bytes(image: Image.Image, size: int) -> bytes:
    resized = image.resize((size, size), Image.Resampling.LANCZOS)
    buf = BytesIO()
    resized.save(buf, format="PNG")
    return buf.getvalue()


def write_icns(image: Image.Image, dest: Path) -> None:
    entries: list[tuple[bytes, bytes]] = []
    for type_code, size in ICNS_TYPES:
        entries.append((type_code.encode("ascii"), _png_bytes(image, size)))
    total = 8 + sum(8 + len(data) for _code, data in entries)
    out = BytesIO()
    out.write(b"icns")
    out.write(struct.pack(">I", total))
    for type_code, data in entries:
        out.write(type_code)
        out.write(struct.pack(">I", 8 + len(data)))
        out.write(data)
    dest.write_bytes(out.getvalue())


def knockout_square_background(image: Image.Image, threshold: int = 28) -> Image.Image:
    """Make the black square around the circular mark transparent."""
    img = image.convert("RGBA")
    pixels = img.load()
    width, height = img.size
    queue: list[tuple[int, int]] = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]
    seen = bytearray(width * height)

    def is_background(x: int, y: int) -> bool:
        red, green, blue, alpha = pixels[x, y]
        return alpha > 0 and red < threshold and green < threshold and blue < threshold

    while queue:
        x, y = queue.pop()
        if x < 0 or y < 0 or x >= width or y >= height:
            continue
        index = y * width + x
        if seen[index]:
            continue
        seen[index] = 1
        if not is_background(x, y):
            continue
        pixels[x, y] = (0, 0, 0, 0)
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    return img


def main() -> None:
    image = knockout_square_background(Image.open(SRC))
    image.save(SRC, format="PNG")
    image.save(
        ICO,
        format="ICO",
        sizes=[(size, size) for size in ICO_SIZES],
    )
    write_icns(image, ICNS)
    print(f"Wrote {SRC}")
    print(f"Wrote {ICO}")
    print(f"Wrote {ICNS}")


if __name__ == "__main__":
    main()
