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
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

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
    (str(ROOT / "assets" / "logo.png"), "assets/logo.png"),
]
if ICNS:
    datas.append((ICNS, "assets"))

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
    "host._macos",
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
    "CFBundleShortVersionString": os.environ.get("WHITEBOARD_VERSION", "0.4.0"),
    "CFBundleVersion": "1",
    "LSMinimumSystemVersion": "11.0",
    "NSHighResolutionCapable": True,
    "LSApplicationCategoryType": "public.app-category.education",
    "NSHumanReadableCopyright": "WhiteBoard",
    # WKWebView's loads sit on URLSession and are therefore subject to App
    # Transport Security, which by default only offers ciphers with forward
    # secrecy. Plenty of Blackboard servers still offer only
    # TLS_RSA_WITH_AES_256_CBC_SHA, and WebKit rejects that with
    # NSURLErrorSecureConnectionFailed (-1200): the load fails instantly and
    # location.href never leaves about:blank.
    #
    # This relaxes the restriction for web content only, leaving anything the
    # app loads through URLSession protected. The school URL is typed in at
    # runtime, so the exception cannot be scoped to one domain. To narrow it,
    # replace this key with:
    #   "NSExceptionDomains": {"<school>": {"NSIncludesSubdomains": True,
    #                                        "NSExceptionRequiresForwardSecrecy": False}}
    "NSAppTransportSecurity": {"NSAllowsArbitraryLoadsInWebContent": True},
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