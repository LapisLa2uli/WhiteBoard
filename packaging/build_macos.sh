#!/usr/bin/env bash
# Build WhiteBoard.app for macOS with PyInstaller.
#
# PyInstaller works on macOS because it produces a real .app bundle, which is
# what WKWebView needs: it traps the process at startup unless NSBundle can find
# an enclosing bundle, and NSBundle does not walk up out of a subdirectory. That
# is the whole reason the host lives inside a bundle rather than beside one.
#
# Needs PyInstaller and pyobjc:
#   .venv/bin/python -m pip install pyinstaller \
#       pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-WebKit
# Point at a different interpreter with PYTHON=/path/to/python
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

APP_NAME="WhiteBoard"
BUNDLE_ID="cn.shs.whiteboard"
VERSION="${WHITEBOARD_VERSION:-0.4.0}"
DIST="${1:-$ROOT/dist}"
APP="$DIST/$APP_NAME.app"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3.12 || command -v python3 || true)"
fi
if [[ -z "$PYTHON" || ! -x "$PYTHON" ]]; then
  echo "No Python found. Create .venv, or set PYTHON=/path/to/python" >&2
  exit 1
fi
if ! "$PYTHON" -c "import PyInstaller" 2>/dev/null; then
  echo "$PYTHON has no PyInstaller. Install it with:" >&2
  echo "  $PYTHON -m pip install pyinstaller" >&2
  exit 1
fi
if ! "$PYTHON" -c "import objc, AppKit, WebKit" 2>/dev/null; then
  echo "$PYTHON has no pyobjc. Install it with:" >&2
  echo "  $PYTHON -m pip install pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-WebKit" >&2
  exit 1
fi
echo "Building $APP_NAME.app $VERSION"
echo "  python:    $PYTHON ($("$PYTHON" -V 2>&1))"

# ---------------------------------------------------------------------------
# Icon
# ---------------------------------------------------------------------------
# The icon is built from a PNG here rather than kept as an .icns in the
# repository. iconutil writes a real multi-representation container; a PNG
# renamed to .icns does not. AppKit sniffs the PNG header, so the Dock icon
# works at runtime, but Finder and LaunchServices go through IconServices, which
# requires the real format and otherwise shows a blank page.
#
# The source PNG is a build input and lives in dist/, which is git-ignored, so
# the repository carries the design files rather than every render of them.
ICON_SOURCE="$DIST/logo-macOS.png"
if [[ ! -f "$ICON_SOURCE" ]]; then
  echo "The icon source is missing." >&2
  echo "Put a 1024x1024 PNG at:" >&2
  echo "  $ICON_SOURCE" >&2
  exit 1
fi
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
ICONSET="$WORK/AppIcon.iconset"
mkdir -p "$ICONSET"
for spec in "16:icon_16x16" "32:icon_16x16@2x" "32:icon_32x32" "64:icon_32x32@2x" \
            "128:icon_128x128" "256:icon_128x128@2x" "256:icon_256x256" \
            "512:icon_256x256@2x" "512:icon_512x512" "1024:icon_512x512@2x"; do
  px="${spec%%:*}"
  name="${spec#*:}"
  sips -s format png -z "$px" "$px" "$ICON_SOURCE" --out "$ICONSET/$name.png" >/dev/null 2>&1
done
if [[ ! -f "$ICONSET/icon_512x512@2x.png" ]]; then
  echo "Could not resize $ICON_SOURCE into an iconset." >&2
  exit 1
fi
ICNS="$WORK/AppIcon.icns"
iconutil -c icns -o "$ICNS" "$ICONSET"
if head -c 4 "$ICNS" | grep -q "icns"; then
  echo "  icon: real icns container, $(ls "$ICONSET" | wc -l | tr -d ' ') sizes"
else
  echo "  WARNING: iconutil did not produce a real icns; Finder will show a blank page." >&2
fi

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
# PyInstaller caches under ~/Library/Application Support. Keep that inside the
# workspace so a build never depends on writing to the home folder.
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$ROOT/build/pyinstaller}"
export WHITEBOARD_ICNS="$ICNS"
export WHITEBOARD_VERSION="$VERSION"

"$PYTHON" -m PyInstaller --noconfirm --clean \
  --distpath "$DIST" --workpath "$ROOT/build/macos" \
  "$ROOT/packaging/whiteboard-macos.spec" 2>&1 | sed 's/^/  /' | tail -5

if [[ ! -d "$APP" ]]; then
  echo "Build finished but $APP was not found." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------
# arm64 will not execute unsigned, so this is not optional. A Developer ID is
# only needed for notarisation, which lets a download run without the user
# having to approve it; ad-hoc is free and works locally.
if command -v codesign >/dev/null 2>&1; then
  SIGN_ID="${SIGN_ID:--}"
  echo "  signing (identity: $SIGN_ID)"

  # Hardened Runtime is required for notarisation. It also enforces library
  # validation, and pyobjc ships extensions that are not signed by the same
  # identity, so the app would refuse to load AppKit and WebKit without this
  # exception.
  ENTITLEMENTS="$WORK/entitlements.plist"
  cat > "$ENTITLEMENTS" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>com.apple.security.cs.disable-library-validation</key><true/>
</dict></plist>
PLIST

  # Every bundled dylib gets the same identity as the app, so nested code is
  # consistent with the bundle rather than signed only by upstream.
  SIGNED_LIBS=0
  while IFS= read -r lib; do
    codesign --force --sign "$SIGN_ID" "$lib" 2>/dev/null && SIGNED_LIBS=$((SIGNED_LIBS + 1))
  done < <(find "$APP/Contents" \( -name "*.so" -o -name "*.dylib" \) -type f)
  echo "  signed $SIGNED_LIBS libraries"

  codesign --force --sign "$SIGN_ID" --options runtime --timestamp=none \
           --entitlements "$ENTITLEMENTS" \
           --identifier "$BUNDLE_ID" "$APP" 2>&1 | sed 's/^/  /' || true

  if codesign --verify --deep --strict "$APP" 2>/dev/null; then
    echo "  signature verifies (hardened runtime on)"
  else
    echo "  WARNING: signature does not verify" >&2
  fi
fi

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
# A build can look entirely correct and still not work: WKWebView traps without
# a bundle identity, a pyobjc framework can be missing, and evaluateJavaScript
# can hand back Objective-C objects that fail every isinstance check
# downstream. Run the real thing before calling this a build.
#
# This asks for --selftest rather than passing -c to the app, because
# PyInstaller's bootloader does not run -c: it launches the app regardless, so
# such a test silently proves only that the app started.
if "$APP/Contents/MacOS/$APP_NAME" --selftest; then
  echo "  smoke test: bundle identity, WebKit, script results and icon all good"
else
  echo "  SMOKE TEST FAILED - the bundle does not work." >&2
  echo "  Run it by hand to see why:" >&2
  echo "    $APP/Contents/MacOS/$APP_NAME --selftest" >&2
  exit 1
fi

SIZE="$(du -sh "$APP" | cut -f1)"
echo
echo "Built $APP  ($SIZE)"
echo "Run it with:  open \"$APP\""
echo
echo "Data folder:  ~/.config/whiteboard"
echo "Sign out:    delete that folder"