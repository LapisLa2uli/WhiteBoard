# -*- mode: python ; coding: utf-8 -*-
"""Package the current WhiteBoard app for Windows. Stdlib plus WebView2."""

from pathlib import Path
import os
import sys

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT))
from version import APP_VERSION
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct
numeric_version = tuple(int(part) for part in APP_VERSION.split('.')) + (0,)
file_version = VSVersionInfo(ffi=FixedFileInfo(filevers=numeric_version, prodvers=numeric_version, mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)), kids=[StringFileInfo([StringTable('040904B0', [StringStruct('ProductName', 'WhiteBoard'), StringStruct('FileDescription', 'WhiteBoard'), StringStruct('FileVersion', APP_VERSION), StringStruct('ProductVersion', APP_VERSION)])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])

datas = [
    (str(ROOT / "static"), "static"),
    (str(ROOT / "assets" / "logo.ico"), "assets"),
    (str(ROOT / "assets" / "logo.png"), "assets"),
    (str(ROOT / "assets" / "webview2"), "assets/webview2"),
]
_auth = ROOT / "authid.txt"
if _auth.is_file():
    datas.append((str(_auth), "."))
if os.environ.get("WHITEBOARD_BUILD_INFO"):
    datas.append((os.environ["WHITEBOARD_BUILD_INFO"], "."))
hiddenimports = [
    "app",
    "app.theme",
    "app.palette",
    "app.filters",
    "app.google_calendar",
    "app.status",
    "blackboard",
    "blackboard.api",
    "blackboard.auth",
    "blackboard.models",
    "blackboard.store",
    "data",
    "accounts",
    "persistence",
    "secure_storage",
    "version",
    "host",
    "host.trust",
    "host._windows",
    "host.windows_smoke",
    "server",
    "session",
    "crawl",
    "present",
    "shortcuts",
]

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "PyQt5", "PyQt6", "IPython", "flet", "playwright"],
    noarchive=False,
)
pyz = PYZ(a.pure)

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
    icon=str(ROOT / "assets" / "logo.ico"),
    version=file_version,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="WhiteBoard",
)
