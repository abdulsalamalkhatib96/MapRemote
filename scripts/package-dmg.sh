#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
APP="$PWD/MapRemote.app"
[[ -d "$APP" ]] || { echo "Build MapRemote.app first"; exit 1; }
ARCH="$(uname -m)"
VERSION="$(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$APP/Contents/Info.plist")"
mkdir -p dist
OUT="$PWD/dist/MapRemote-${VERSION}-${ARCH}.dmg"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
NOTARY_ARGS=()
if [[ -n "${MAPREMOTE_NOTARY_KEYCHAIN:-}" ]]; then
  NOTARY_ARGS=(--keychain "$MAPREMOTE_NOTARY_KEYCHAIN")
fi
/usr/bin/ditto "$APP" "$STAGE/MapRemote.app"
ln -s /Applications "$STAGE/Applications"
# Notarize and staple the app before wrapping it, so it also works offline.
if [[ -n "${MAPREMOTE_NOTARY_PROFILE:-}" ]]; then
  [[ -n "${MAPREMOTE_SIGN_IDENTITY:-}" && "$MAPREMOTE_SIGN_IDENTITY" != "-" ]] || { echo "Developer ID required for notarization"; exit 1; }
  /usr/bin/ditto -c -k --keepParent "$STAGE/MapRemote.app" "$STAGE/notary.zip"
  /usr/bin/xcrun notarytool submit "$STAGE/notary.zip" --keychain-profile "$MAPREMOTE_NOTARY_PROFILE" ${NOTARY_ARGS[@]+"${NOTARY_ARGS[@]}"} --wait
  /usr/bin/xcrun stapler staple "$STAGE/MapRemote.app"
  /usr/bin/xcrun stapler validate "$STAGE/MapRemote.app"
  rm "$STAGE/notary.zip"
fi
/usr/bin/hdiutil create -ov -volname "MapRemote" -srcfolder "$STAGE" -format UDZO "$OUT"
/usr/bin/hdiutil verify "$OUT"
if [[ -n "${MAPREMOTE_SIGN_IDENTITY:-}" && "$MAPREMOTE_SIGN_IDENTITY" != "-" ]]; then
  /usr/bin/codesign --force --timestamp --sign "$MAPREMOTE_SIGN_IDENTITY" "$OUT"
fi
if [[ -n "${MAPREMOTE_NOTARY_PROFILE:-}" ]]; then
  /usr/bin/xcrun notarytool submit "$OUT" --keychain-profile "$MAPREMOTE_NOTARY_PROFILE" ${NOTARY_ARGS[@]+"${NOTARY_ARGS[@]}"} --wait
  /usr/bin/xcrun stapler staple "$OUT"
  /usr/bin/xcrun stapler validate "$OUT"
  /usr/sbin/spctl -a -t open --context context:primary-signature -v "$OUT"
fi
(cd dist && /usr/bin/shasum -a 256 "$(basename "$OUT")" > "$(basename "$OUT").sha256")
echo "$OUT"
