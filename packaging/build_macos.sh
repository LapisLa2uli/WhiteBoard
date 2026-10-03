#!/usr/bin/env bash
# Build WhiteBoard.app for macOS: a python-build-standalone interpreter and
# everything it needs, inside one self-contained bundle.
#
# Two rules make this work, and both are easy to break:
#
#   1. Contents/MacOS/WhiteBoard must BE the interpreter. WKWebView traps the
#      process if NSBundle cannot find an enclosing bundle, and NSBundle does
#      not walk up out of a subdirectory, so a launcher script in MacOS that
#      execs a python further inside the bundle loses the bundle identity and
#      the window dies at startup.
#
#   2. Contents/MacOS/WhiteBoard._pth puts the interpreter in isolated mode,
#      which is what makes the bundle relocatable. Standalone builds otherwise
#      hard-code the prefix they were built at and fail to find their stdlib.
#
# Usage: packaging/build_macos.sh [output-dir]
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

APP_NAME="WhiteBoard"
BUNDLE_ID="cn.shs.whiteboard"
DIST="${1:-$ROOT/dist}"
APP="$DIST/$APP_NAME.app"

# The interpreter, the standard library, and pyobjc all come from one
# python-build-standalone archive unpacked under dist/. That folder is git-ignored,
# so the runtime is a local build input rather than something the repository pins.
# Any folder under dist/ holding lib/python3.X is picked up, so the archive can be
# named after whatever version it is:
#
#   curl -LO https://github.com/astral-sh/python-build-standalone/releases/\
#     download/<tag>/cpython-3.12.15+<tag>-aarch64-apple-darwin-install_only_stripped.tar.gz
#   mkdir -p dist/cp3.12-aarch64
#   tar -xzf ... -C dist/cp3.12-aarch64 --strip-components=1
#   dist/cp3.12-aarch64/bin/python3.12 -m pip install --target \
#     dist/cp3.12-aarch64/lib/python3.12/site-packages \
#     pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-WebKit
#
# 3.12 is the version to use. 3.10 is 1.7 MB smaller unpacked, but it ignores
# relative paths in a ._pth file and cannot be made relocatable without pinning
# the bundle to the path it was built at. Do not judge size by the .tar.gz
# number: compressed download size ranks these the other way round.
# Override the location with PYTHON_RUNTIME=...
if [[ -z "${PYTHON_RUNTIME:-}" ]]; then
  PYTHON_RUNTIME=""
  for candidate in "$DIST" "$DIST"/*; do
    [[ -d "$candidate/lib" ]] || continue
    compgen -G "$candidate/lib/python3.*" > /dev/null 2>&1 || continue
    if [[ -n "$PYTHON_RUNTIME" ]]; then
      echo "More than one Python runtime under $DIST:" >&2
      echo "  $PYTHON_RUNTIME" >&2
      echo "  $candidate" >&2
      echo "Name one with PYTHON_RUNTIME=/path/to/runtime" >&2
      exit 1
    fi
    PYTHON_RUNTIME="$candidate"
  done
fi
if [[ -z "$PYTHON_RUNTIME" || ! -d "$PYTHON_RUNTIME/lib" ]]; then
  echo "No Python runtime found under $DIST." >&2
  echo "Unpack a python-build-standalone install_only_stripped archive into" >&2
  echo "a folder there; it must contain bin/python3.X and lib/python3.X." >&2
  echo "Set PYTHON_RUNTIME=/path/to/runtime to override." >&2
  exit 1
fi

# Work out the runtime's minor version from its layout rather than assuming 3.14,
# so a 3.12 or 3.13 runtime can be dropped in unchanged.
PY_VER=""
for candidate in "$PYTHON_RUNTIME"/lib/python3.*; do
  [[ -d "$candidate" ]] || continue
  PY_VER="$(basename "$candidate")"
  break
done
if [[ -z "$PY_VER" ]]; then
  echo "No lib/python3.X directory under $PYTHON_RUNTIME." >&2
  exit 1
fi
if [[ ! -x "$PYTHON_RUNTIME/bin/$PY_VER" ]]; then
  echo "Runtime has lib/$PY_VER but no bin/$PY_VER executable." >&2
  exit 1
fi

# pyobjc is the one third-party dependency. It is installed into the runtime's
# own site-packages, so the runtime folder is the single complete build input
# and the extension modules are built by the very interpreter that ships them.
SITE_PACKAGES="$PYTHON_RUNTIME/lib/$PY_VER/site-packages"
MISSING=""
for package in objc AppKit WebKit Foundation; do
  [[ -d "$SITE_PACKAGES/$package" ]] || MISSING="$MISSING $package"
done
if [[ -n "$MISSING" ]]; then
  echo "The runtime at $PYTHON_RUNTIME is missing pyobjc:$MISSING" >&2
  echo "Install it into the runtime:" >&2
  echo "  $PYTHON_RUNTIME/bin/$PY_VER -m pip install --target \\" >&2
  echo "      $SITE_PACKAGES \\" >&2
  echo "      pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-WebKit" >&2
  exit 1
fi

echo "Building $APP_NAME.app"
echo "  runtime:   $PYTHON_RUNTIME ($PY_VER, pyobjc included)"
echo "  bundle id: $BUNDLE_ID"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/app"

# Copied, not symlinked, so the finished bundle can be moved anywhere.
mkdir -p "$APP/Contents/Resources/python"
cp -R "$PYTHON_RUNTIME/lib" "$APP/Contents/Resources/python/lib"
cp "$PYTHON_RUNTIME/bin/$PY_VER" "$APP/Contents/MacOS/$APP_NAME"
chmod +x "$APP/Contents/MacOS/$APP_NAME"

# Strip build-time and developer material. None of this is importable at
# runtime, and together it is most of the bundle. install_only_stripped only
# removes debug symbols, so it still ships all of this: the saving happens here.
#
#   config-3.x-darwin   69 MB  headers, static libpython, Makefile
#   test                36 MB  the CPython test suite
#   Tcl/Tk + itcl      ~10 MB  unused, tkinter was already removed above
#   ensurepip + pip     8 MB  package installer
#   idlelib             2 MB  the bundled editor
#   pydoc_data         600 KB  help() topics
PY_LIB="$APP/Contents/Resources/python/lib/$PY_VER"
rm -rf "$PY_LIB"/config-3.* "$PY_LIB"/config-* "$PY_LIB/test" "$PY_LIB/idlelib" \
       "$PY_LIB/ensurepip" "$PY_LIB/pydoc_data" "$PY_LIB/lib2to3" \
       "$PY_LIB/tkinter" "$PY_LIB/site-packages/pip" \
       "$PY_LIB/site-packages"/pip-*.dist-info "$PY_LIB/site-packages"/setuptools \
       "$PY_LIB/site-packages"/pkg_resources "$PY_LIB/site-packages"/_distutils_hack \
       "$PY_LIB/site-packages"/distutils-precedence.pth "$PY_LIB"/idlelib \
       "$PY_LIB"/ensurepip "$PY_LIB"/site-packages/*.pth

# Sibling directories under lib/, not lib/python3.X: the Tcl/Tk stack and
# thread library, which exist only for tkinter, plus the build-time libpython
# (this build links statically, so nothing needs it at runtime).
PY_PARENT="$(dirname "$PY_LIB")"
rm -rf "$PY_PARENT"/tcl* "$PY_PARENT"/tk* "$PY_PARENT"/itcl* "$PY_PARENT"/thread* \
       "$PY_PARENT"/pkgconfig "$PY_PARENT"/libtcl*.dylib \
       "$PY_PARENT"/libpython"$PY_VER".dylib
find "$PY_PARENT" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$PY_PARENT" -name "*.a" -type f -delete 2>/dev/null || true

# pyobjc came in with the copied lib/ tree above, so there is nothing left to
# copy separately. PyObjCTest is a test helper and is not part of the bridge.
rm -rf "$PY_LIB/site-packages/PyObjCTest"

# The app itself.
cp "$ROOT/run.py" "$ROOT/data.py" "$ROOT/server.py" "$ROOT/session.py" \
   "$ROOT/crawl.py" "$ROOT/present.py" "$ROOT/shortcuts.py" \
   "$APP/Contents/Resources/app/"
cp -R "$ROOT/host" "$ROOT/app" "$ROOT/blackboard" "$ROOT/static" "$ROOT/assets" \
      "$APP/Contents/Resources/app/"

# App icon. This has to sit in Contents/Resources, because CFBundleIconFile
# names a resource rather than a path, and AppKit resolves it from there. The
# Dock, Finder and Spotlight all read the same file, so one copy is enough.
ICON_NAME="AppIcon"
if [[ ! -f "$ROOT/assets/$ICON_NAME.icns" ]]; then
  echo "assets/$ICON_NAME.icns is missing." >&2
  echo "Export one from Icon Composer (or assets/logo.icon) and retry." >&2
  exit 1
fi
cp "$ROOT/assets/$ICON_NAME.icns" "$APP/Contents/Resources/$ICON_NAME.icns"

# Isolated mode, with paths relative to the bundle (rule 2). The trailing
# "import site" is what re-enables sitecustomize in isolated mode; without it
# Python skips site processing and the app never starts.
#
# The relative paths matter: this is what makes the bundle relocatable, and it
# is not supported by every CPython. 3.10 silently ignores relative entries in
# a ._pth file and falls back to the prefix baked in at build time, which only
# resolves on the machine that built it. The smoke test below catches that.
cat > "$APP/Contents/MacOS/$APP_NAME._pth" <<PTH
../Resources/python/lib/$PY_VER
../Resources/python/lib/$PY_VER/lib-dynload
../Resources/python/lib/$PY_VER/site-packages
import site
PTH

# Start the app when the bundle is launched with no arguments, which is what a
# double-click does. Also stops Python writing __pycache__ into the bundle,
# which would invalidate the code signature on every launch.
cat > "$PY_LIB/site-packages/sitecustomize.py" <<'PY'
import os
import runpy
import sys

# Writing .pyc files into the bundle would break the code signature.
sys.dont_write_bytecode = True

_APP = os.path.normpath(os.path.join(sys.prefix, "..", "Resources", "app"))

# Launched by double-click, i.e. with no script argument. Anything else (a -c
# probe, a passed path) is left alone so the bundle stays debuggable. This
# compares against a leading "-" rather than sys.executable, because argv[0]
# is whatever path was used to exec the bundle and may be relative.
_launched_bare = len(sys.argv) == 1 and not str(sys.argv[0]).startswith("-")

if _launched_bare and os.path.isdir(_APP):
    # run_path does not add the folder to sys.path in isolated mode.
    if _APP not in sys.path:
        sys.path.insert(0, _APP)
    runpy.run_path(os.path.join(_APP, "run.py"), run_name="__main__")
PY

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>$APP_NAME</string>
  <key>CFBundleExecutable</key><string>$APP_NAME</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.3.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleIconFile</key><string>$ICON_NAME</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSApplicationCategoryType</key><string>public.app-category.education</string>
  <key>NSHumanReadableCopyright</key><string>WhiteBoard</string>
</dict>
</plist>
PLIST

# Precompile so no bytecode is written at runtime (see sitecustomize above).
"$APP/Contents/MacOS/$APP_NAME" -m compileall -q "$APP/Contents/Resources/app" >/dev/null 2>&1 || true

# Ad-hoc signature. arm64 requires a signature to execute at all, and an
# ad-hoc one is free. A Developer ID is only needed for notarisation, which
# lets a download run without a right-click -> Open.
if command -v codesign >/dev/null 2>&1; then
  SIGN_ID="${SIGN_ID:--}"
  echo "  signing (identity: $SIGN_ID)"

  # Hardened Runtime is not optional: Apple rejects anything notarised without
  # it. It also enforces library validation, and pyobjc ships extensions that
  # are not signed by the same identity, so the app would refuse to load
  # AppKit and WebKit without this exception.
  ENTITLEMENTS="$(mktemp).plist"
  cat > "$ENTITLEMENTS" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>com.apple.security.cs.disable-library-validation</key><true/>
</dict></plist>
PLIST

  # Every bundled dylib gets the same identity as the app, so the nested code is
  # consistent with the bundle rather than only ad-hoc signed by upstream.
  SIGNED_LIBS=0
  while IFS= read -r lib; do
    codesign --force --sign "$SIGN_ID" "$lib" 2>/dev/null && SIGNED_LIBS=$((SIGNED_LIBS + 1))
  done < <(find "$APP/Contents/Resources" -name "*.so" -type f)
  echo "  signed $SIGNED_LIBS libraries"

  # The interpreter must be Contents/MacOS/WhiteBoard (see the note at the top
  # of this file), and CPython only looks for its ._pth beside the executable.
  # That puts a plain text file inside the code directory, so it needs its own
  # signature or the bundle will not verify.
  codesign --force --sign "$SIGN_ID" "$APP/Contents/MacOS/$APP_NAME._pth" 2>/dev/null || true
  codesign --force --sign "$SIGN_ID" --options runtime --timestamp=none \
           --entitlements "$ENTITLEMENTS" \
           --identifier "$BUNDLE_ID" "$APP" 2>&1 | sed 's/^/  /' || true
  rm -f "$ENTITLEMENTS"

  if codesign --verify --deep --strict "$APP" 2>/dev/null; then
    echo "  signature verifies (hardened runtime on)"
  else
    echo "  WARNING: signature does not verify" >&2
  fi
fi

# Prove the bundle actually boots before calling this a build. Everything above
# can look right while the interpreter still cannot find its standard library:
# 3.10 silently ignores relative ._pth entries, and a static check would not see
# it. Running it from a different directory also proves the bundle still resolves
# its own paths, which is what makes it relocatable.
PROBE_DIR="$(mktemp -d)"
trap 'rm -rf "$PROBE_DIR"' EXIT
if (cd "$PROBE_DIR" && "$APP/Contents/MacOS/$APP_NAME" -c "
import os, sys, Foundation, objc, AppKit, WebKit
bundle = Foundation.NSBundle.mainBundle().bundleIdentifier()
if not bundle:
    raise SystemExit('no bundle identity')
# sys.prefix is the directory holding the executable, so the bundle resolved its
# own stdlib rather than falling back to the prefix baked in at build time.
if os.path.realpath(sys.prefix) != os.path.realpath(os.path.dirname(sys.executable)):
    raise SystemExit('not relocatable: prefix=%s exe=%s' % (sys.prefix, sys.executable))
if not any('lib/python' in p for p in sys.path):
    raise SystemExit('standard library not found on sys.path: %r' % sys.path)
" >/dev/null 2>&1); then
  echo "  smoke test: boots, relocatable, WebKit loads"
else
  echo "  SMOKE TEST FAILED - the bundle does not start." >&2
  echo "  Run it by hand to see why:" >&2
  echo "    (cd /tmp && $APP/Contents/MacOS/$APP_NAME -c pass)" >&2
  exit 1
fi

SIZE="$(du -sh "$APP" | cut -f1)"
echo
echo "Built $APP  ($SIZE)"
echo "Run it with:  open \"$APP\""
echo
echo "Data folder:  ~/.config/whiteboard"
echo "Sign out:    delete that folder"