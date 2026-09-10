# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for WhiteBoard (Windows onedir and macOS .app)."""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(SPECPATH).resolve().parent
block_cipher = None

datas = [(str(ROOT / "assets"), "assets")]
datas += collect_data_files("flet")
binaries = []
hiddenimports = [
    "app",
    "blackboard",
    "flet",
    "playwright",
    "playwright.sync_api",
    "playwright.async_api",
]

for package in ("playwright",):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

icon = str(ROOT / ("assets/logo.icns" if sys.platform == "darwin" else "assets/logo.ico"))

a = Analysis(
    [str(ROOT / "run_whiteboard.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
            "NSHighResolutionCapable": True,
        },
    )
