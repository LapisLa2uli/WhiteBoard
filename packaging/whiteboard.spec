# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for WhiteBoard (Windows onedir and macOS .app)."""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(SPECPATH).resolve().parent
block_cipher = None

try:
    import flet_desktop.version  # noqa: F401
except ImportError as exc:
    raise SystemExit(
        "flet-desktop must be installed before packaging. "
        "Run: python -m pip install flet-desktop"
    ) from exc

datas = [(str(ROOT / "assets"), "assets")]
datas += collect_data_files("flet")
binaries = []
hiddenimports = [
    "app",
    "blackboard",
    "flet",
    "flet_desktop",
    "flet_desktop.version",
    "playwright",
    "playwright.sync_api",
    "playwright.async_api",
]
hookspath = []

for package in ("flet", "flet_desktop", "playwright"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

try:
    import flet_cli

    hook_dir = Path(flet_cli.__file__).resolve().parent / "__pyinstaller"
    if hook_dir.is_dir():
        hookspath.append(str(hook_dir))
except Exception:
    pass

icon = str(ROOT / ("assets/logo.icns" if sys.platform == "darwin" else "assets/logo.ico"))
version_file = ROOT / "packaging" / "file_version_info.txt"
sys.path.insert(0, str(ROOT))
try:
    from app.branding import APP_VERSION
except Exception:
    APP_VERSION = "0.1.2"

a = Analysis(
    [str(ROOT / "run_whiteboard.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=hookspath,
    hooksconfig={},
    runtime_hooks=[str(ROOT / "packaging" / "rthooks" / "pyi_rth_whiteboard.py")],
    excludes=["matplotlib", "flet.testing", "numpy"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WhiteBoard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=icon,
    version=str(version_file) if version_file.exists() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WhiteBoard",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="WhiteBoard.app",
        icon=str(ROOT / "assets" / "logo.icns"),
        bundle_identifier="com.whiteboard.app",
        info_plist={
            "CFBundleDisplayName": "WhiteBoard",
            "CFBundleName": "WhiteBoard",
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
        },
    )
