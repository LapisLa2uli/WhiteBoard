#!/usr/bin/env bash
# Native Apple silicon build; WHITEBOARD_RELEASE=1 requires signing/notarization.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
DIST="${1:-$ROOT/dist}"
mkdir -p "$DIST"
DIST="$(cd "$DIST" && pwd)"
APP="$DIST/WhiteBoard.app"
RELEASE="${WHITEBOARD_RELEASE:-0}"
SIGN_ID="${SIGN_ID:--}"
export SIGN_ID
"$PYTHON" packaging/check_environment.py macos
VERSION="$("$PYTHON" -c 'from version import APP_VERSION; print(APP_VERSION)')"
PREPARE_ARGS=(macos)
if [[ "$RELEASE" == 1 ]]; then
  [[ "$SIGN_ID" == "Developer ID Application:"* ]] || { echo "Set SIGN_ID to a Developer ID Application identity" >&2; exit 1; }
  [[ -n "${NOTARY_PROFILE:-}" ]] || { echo "Set NOTARY_PROFILE to your notarytool Keychain profile" >&2; exit 1; }
  PREPARE_ARGS+=(--release)
fi
"$PYTHON" packaging/prepare.py "${PREPARE_ARGS[@]}"
export WHITEBOARD_BUILD_INFO="$ROOT/build/macos/build-info.json"
export PYINSTALLER_CONFIG_DIR="$ROOT/build/pyinstaller-cache"
export PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR=1
export PYINSTALLER_VERIFY_BUNDLE_SIGNATURE=1
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
ICONSET="$WORK/AppIcon.iconset"
mkdir -p "$ICONSET"
for spec in "16:icon_16x16" "32:icon_16x16@2x" "32:icon_32x32" "64:icon_32x32@2x" \
            "128:icon_128x128" "256:icon_128x128@2x" "256:icon_256x256" \
            "512:icon_256x256@2x" "512:icon_512x512" "1024:icon_512x512@2x"; do
  sips -s format png -z "${spec%%:*}" "${spec%%:*}" "$ROOT/assets/logo.icon/Assets/logo.png" --out "$ICONSET/${spec#*:}.png" >/dev/null
done
export WHITEBOARD_ICNS="$WORK/AppIcon.icns"
iconutil -c icns -o "$WHITEBOARD_ICNS" "$ICONSET"
export WHITEBOARD_ENTITLEMENTS="$ROOT/packaging/entitlements.plist"
"$PYTHON" -m PyInstaller --noconfirm --clean --distpath "$DIST" --workpath "$ROOT/build/macos" "$ROOT/packaging/whiteboard-macos.spec"
# PyInstaller signs every collected binary with SIGN_ID; failure is fatal.
SIGN_ARGS=(--force --sign "$SIGN_ID" --options runtime --entitlements "$WHITEBOARD_ENTITLEMENTS")
if [[ "$SIGN_ID" == '-' ]]; then SIGN_ARGS+=(--timestamp=none); else SIGN_ARGS+=(--timestamp); fi
codesign "${SIGN_ARGS[@]}" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
[[ "$(lipo -archs "$APP/Contents/MacOS/WhiteBoard")" == 'arm64' ]] || { echo "Wrong executable architecture" >&2; exit 1; }
WHITEBOARD_DATA_DIR="$WORK/smoke-profile" "$APP/Contents/MacOS/WhiteBoard" --selftest

if [[ "$RELEASE" == 1 ]]; then
  ditto -c -k --keepParent "$APP" "$WORK/WhiteBoard.zip"
  xcrun notarytool submit "$WORK/WhiteBoard.zip" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$APP"
  xcrun stapler validate "$APP"
  spctl --assess --type execute --verbose=2 "$APP"
fi
mkdir "$WORK/image"
ditto "$APP" "$WORK/image/WhiteBoard.app"
ln -s /Applications "$WORK/image/Applications"
DMG="$DIST/WhiteBoard-$VERSION-AppleSilicon.dmg"
hdiutil create -ov -volname "WhiteBoard $VERSION" -srcfolder "$WORK/image" -format UDZO "$DMG"
if [[ "$RELEASE" == 1 ]]; then
  codesign --force --sign "$SIGN_ID" --timestamp "$DMG"
  xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$DMG"
  xcrun stapler validate "$DMG"
  codesign --verify --strict "$DMG"
fi
(cd "$DIST" && shasum -a 256 "$(basename "$DMG")" > SHA256SUMS-macos.txt)
cp "$WHITEBOARD_BUILD_INFO" "$DIST/build-info-macos.json"
echo "Built $DMG. Release signing/notarization enabled: $RELEASE"
