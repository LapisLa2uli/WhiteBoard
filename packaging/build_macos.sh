#!/usr/bin/env bash
set -euo pipefail
set -x
cd "$(dirname "$0")/.."

if command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  PYTHON=python3
fi

# Keep the bundled bootloader/extensions runnable on Intel Ventura (13) and later.
export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-11.0}"

ARCH="$("$PYTHON" -c "import platform; print(platform.machine())")"
echo "Packaging WhiteBoard for macOS ($ARCH) with $PYTHON"
"$PYTHON" -c "import sys, platform; print('executable', sys.executable); print('machine', platform.machine())"

if [[ -n "${EXPECTED_ARCH:-}" && "$ARCH" != "$EXPECTED_ARCH" ]]; then
  echo "Python architecture is $ARCH but this job expects $EXPECTED_ARCH" >&2
  exit 1
fi

"$PYTHON" -c "import PyInstaller" >/dev/null 2>&1 || "$PYTHON" -m pip install --default-timeout=120 -r packaging/requirements-build.txt
"$PYTHON" -c "import PIL" >/dev/null 2>&1 || "$PYTHON" -m pip install --default-timeout=120 pillow

"$PYTHON" packaging/generate_icons.py

"$PYTHON" -c "import flet_desktop.version as v; print('flet-desktop', v.version)"
"$PYTHON" packaging/release_notes.py --check

"$PYTHON" packaging/bundle_runtime.py prepare

"$PYTHON" -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/whiteboard.spec

if [[ ! -d dist/WhiteBoard.app ]]; then
  echo "Build finished but dist/WhiteBoard.app was not found" >&2
  exit 1
fi

APP_BIN="dist/WhiteBoard.app/Contents/MacOS/WhiteBoard"
if [[ ! -f "$APP_BIN" ]]; then
  echo "Build finished but $APP_BIN was not found" >&2
  exit 1
fi

ACTUAL_ARCH="$(lipo -archs "$APP_BIN")"
echo "Built binary architectures: $ACTUAL_ARCH"
if ! echo "$ACTUAL_ARCH" | grep -qw "$ARCH"; then
  echo "Expected $ARCH in $APP_BIN but lipo reported: $ACTUAL_ARCH" >&2
  exit 1
fi
if [[ "$ARCH" == "arm64" ]] && echo "$ACTUAL_ARCH" | grep -qw x86_64; then
  echo "Apple Silicon build unexpectedly contains x86_64" >&2
  exit 1
fi
if [[ "$ARCH" == "x86_64" ]] && echo "$ACTUAL_ARCH" | grep -qw arm64; then
  echo "Intel build unexpectedly contains arm64" >&2
  exit 1
fi

"$PYTHON" packaging/bundle_runtime.py verify

echo "Creating installer disk image..."
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/whiteboard-dmg.XXXXXX")"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

cp -R dist/WhiteBoard.app "$STAGE/WhiteBoard.app"
ln -s /Applications "$STAGE/Applications"

DMG="dist/WhiteBoard-${ARCH}.dmg"
rm -f "$DMG"
hdiutil create \
  -volname "WhiteBoard" \
  -srcfolder "$STAGE" \
  -ov \
  -format UDZO \
  "$DMG"

echo "macOS app is at dist/WhiteBoard.app"
echo "Installer disk image is at $DMG"
echo "Open the .dmg and drag WhiteBoard into Applications."
echo "On first launch the app asks before adding Desktop and Spotlight/Applications shortcuts."
