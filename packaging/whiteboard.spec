# -*- mode: python ; coding: utf-8 -*-
"""Package the current WhiteBoard app for Windows. Stdlib plus WebView2."""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "static"), "static"),
    (str(ROOT / "assets"), "assets"),
]
hiddenimports = [
    "app",
    "app.theme",
    "app.palette",
    "app.filters",
    "app.google_calendar",
    "blackboard",
    "blackboard.api",
    "blackboard.auth",
    "blackboard.models",
    "blackboard.store",
    "data",
    "host",
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
