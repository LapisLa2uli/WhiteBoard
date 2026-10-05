# -*- mode: python ; coding: utf-8 -*-
"""Package the current WhiteBoard app for Windows. Stdlib plus WebView2."""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "static"), "static"),
    (str(ROOT / "assets" / "logo.ico"), "assets"),
    (str(ROOT / "assets" / "logo.png"), "assets"),
    (str(ROOT / "assets" / "webview2"), "assets/webview2"),
]
_auth = ROOT / "authid.txt"
if _auth.is_file():
    datas.append((str(_auth), "."))
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
