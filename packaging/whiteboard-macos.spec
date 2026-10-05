# -*- mode: python ; coding: utf-8 -*-
"""Package the current WhiteBoard app for macOS.

PyInstaller bundles the interpreter and only the standard library modules the
app actually imports, which is why this is a fraction of the size of shipping a
whole Python installation.

The macOS window host is WKWebView, which traps the process at startup unless
NSBundle can find an enclosing bundle. BUNDLE() is what supplies one: the
executable ends up at Contents/MacOS/WhiteBoard, inside a real .app, so
NSBundle.mainBundle() resolves and the window opens.
"""

import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT))
from version import APP_VERSION

# The build script generates a real .icns from assets/logo-macOS.png before
# invoking this spec, and points the path here.
ICNS = os.environ.get("WHITEBOARD_ICNS", "")

# Only what the app reads at runtime goes in the bundle. assets/ also holds the
# DMG canvas template, its background, the 1024px PNG the icon is built from,
# and the Icon Composer source: roughly 7.9 MB of build input that would
# otherwise ship to every user.
datas = [
    (str(ROOT / "static"), "static"),
    # Fallback for the static file server's /logo route.
    (str(ROOT / "assets" / "logo.png"), "assets"),
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
    "host._macos",
    "host.trust",
    "server",
    "session",
    "crawl",
    "present",
    "shortcuts",
    # pyobjc loads these frameworks at runtime through objc.loadBundle, so
    # static import analysis never sees them. Without these the app builds
    # cleanly and then dies on the first AppKit call.
    "objc",
    "Foundation",
    "AppKit",
    "Cocoa",
    "CoreFoundation",
    "WebKit",
    "JavaScriptCore",
    "PyObjCTools",
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
    target_arch="arm64",
    codesign_identity=os.environ.get("SIGN_ID") or None,
    entitlements_file=os.environ.get("WHITEBOARD_ENTITLEMENTS") or None,
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

info_plist = {
    "CFBundleName": "WhiteBoard",
    "CFBundleDisplayName": "WhiteBoard",
    "CFBundleShortVersionString": APP_VERSION,
    "CFBundleVersion": APP_VERSION,
    "LSMinimumSystemVersion": "11.0",
    "NSHighResolutionCapable": True,
    "LSApplicationCategoryType": "public.app-category.education",
    "NSHumanReadableCopyright": "WhiteBoard",
    # Scoped compatibility for the documented school; all other hosts use ATS defaults.
    "NSAppTransportSecurity": {"NSExceptionDomains": {
        "shs.blackboardchina.cn": {"NSExceptionRequiresForwardSecrecy": False}
    }},
}
if ICNS:
    info_plist["CFBundleIconFile"] = os.path.splitext(os.path.basename(ICNS))[0]

app = BUNDLE(
    coll,
    name="WhiteBoard.app",
    icon=ICNS or None,
    bundle_identifier="cn.shs.whiteboard",
    info_plist=info_plist,
)
