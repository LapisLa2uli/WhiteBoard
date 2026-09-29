"""Write a PyInstaller Windows VERSIONINFO resource from app.branding."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.branding import APP_NAME, APP_PUBLISHER, APP_VERSION

DEST = Path(__file__).resolve().parent / "file_version_info.txt"


def version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = []
    for piece in version.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits or "0"))
    while len(parts) < 4:
        parts.append(0)
    return (parts[0], parts[1], parts[2], parts[3])


def main() -> None:
    major, minor, patch, build = version_tuple(APP_VERSION)
    dest = DEST
    dest.write_text(
        "\n".join(
            [
                "# UTF-8",
                "VSVersionInfo(",
                "  ffi=FixedFileInfo(",
                f"    filevers=({major}, {minor}, {patch}, {build}),",
                f"    prodvers=({major}, {minor}, {patch}, {build}),",
                "    mask=0x3f,",
                "    flags=0x0,",
                "    OS=0x40004,",
                "    fileType=0x1,",
                "    subtype=0x0,",
                "    date=(0, 0)",
                "  ),",
                "  kids=[",
                "    StringFileInfo([",
                "      StringTable(",
                "        '040904B0',",
                "        [",
                f"          StringStruct('CompanyName', '{APP_PUBLISHER}'),",
                f"          StringStruct('FileDescription', '{APP_NAME}'),",
                f"          StringStruct('FileVersion', '{APP_VERSION}'),",
                f"          StringStruct('InternalName', '{APP_NAME}'),",
                f"          StringStruct('OriginalFilename', '{APP_NAME}.exe'),",
                f"          StringStruct('ProductName', '{APP_NAME}'),",
                f"          StringStruct('ProductVersion', '{APP_VERSION}')",
                "        ]",
                "      )",
                "    ]),",
                "    VarFileInfo([VarStruct('Translation', [1033, 1200])])",
                "  ]",
                ")",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Wrote {dest}")


if __name__ == "__main__":
    main()
