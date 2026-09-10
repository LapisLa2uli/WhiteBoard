#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -c "import PyInstaller" >/dev/null 2>&1 || python3 -m pip install --default-timeout=120 -r packaging/requirements-build.txt
python3 -c "import PIL" >/dev/null 2>&1 || python3 -m pip install --default-timeout=120 pillow

python3 packaging/generate_icons.py

echo "Packaging WhiteBoard for macOS..."
python3 -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/whiteboard.spec

if [[ ! -d dist/WhiteBoard.app ]]; then
  echo "Build finished but dist/WhiteBoard.app was not found" >&2
  exit 1
fi

echo "Creating installer disk image..."
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/whiteboard-dmg.XXXXXX")"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

cp -R dist/WhiteBoard.app "$STAGE/WhiteBoard.app"
ln -s /Applications "$STAGE/Applications"

DMG="dist/WhiteBoard.dmg"
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
