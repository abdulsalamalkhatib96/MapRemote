#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ "$(uname -s)" != Darwin ]]; then echo 'This app builds on macOS only.'; exit 1; fi
if ! /usr/bin/xcode-select -p >/dev/null 2>&1; then
  echo 'Install Apple Command Line Tools: xcode-select --install'; exit 1
fi
# A build-machine interpreter is needed only to assemble the standalone runtime.
BUILD_PYTHON="${MAPREMOTE_BUILD_PYTHON:-$(command -v python3 || true)}"
[[ -n "$BUILD_PYTHON" ]] || { echo 'Python 3 is required on the build machine only.'; exit 1; }
APP="$PWD/MapRemote.app"
[[ ! -e "$APP" ]] || { echo 'Existing MapRemote.app found. Close it and move it out before rebuilding.'; exit 1; }
TMP="$(mktemp -d "${TMPDIR:-/tmp}/mapremote-build.XXXXXXXX")"
trap 'rm -rf "$TMP"' EXIT
CONTENTS="$TMP/MapRemote.app/Contents"
mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Resources" "$CONTENTS/Helpers"
export MACOSX_DEPLOYMENT_TARGET=12.0
# Sign outside the enclosing app for an independently executable tool.
/usr/bin/xcrun swiftc -swift-version 5 -O -framework SystemConfiguration ProxyHelper.swift -o "$TMP/ProxyHelper"
SIGN_ID="${MAPREMOTE_SIGN_IDENTITY:--}"
if [[ "$SIGN_ID" == "-" ]]; then
  /usr/bin/codesign --force --sign - --timestamp=none --identifier com.mapremote.proxyhelper "$TMP/ProxyHelper"
else
  /usr/bin/codesign --force --sign "$SIGN_ID" --timestamp --options runtime --identifier com.mapremote.proxyhelper "$TMP/ProxyHelper"
fi
/usr/bin/codesign --verify --strict --verbose=2 "$TMP/ProxyHelper"
/usr/bin/ditto "$TMP/ProxyHelper" "$CONTENTS/Helpers/ProxyHelper"
/usr/bin/xcrun swiftc -swift-version 5 -O -framework AppKit -framework WebKit NativeApp.swift -o "$CONTENTS/MacOS/MapRemote"
cp app.py addon.py rules.py system_proxy.py index.html engine_entry.py smoke_test.py "$CONTENTS/Resources/"
cp Info.plist "$CONTENTS/Info.plist"
bash scripts/build-icon.sh "$CONTENTS/Resources/MapRemote.icns"
"$BUILD_PYTHON" scripts/bundle-runtime.py "$CONTENTS/Resources/runtime"
cp scripts/mitmdump-launcher.sh "$CONTENTS/Resources/mitmdump"
chmod 755 "$CONTENTS/Resources/mitmdump"
"$BUILD_PYTHON" scripts/sign-app.py "$TMP/MapRemote.app"
/usr/bin/ditto "$TMP/MapRemote.app" "$APP"
/usr/bin/codesign --verify --deep --strict --verbose=4 "$APP"
if [[ "${MAPREMOTE_BUILD_ONLY:-0}" != 1 ]]; then /usr/bin/open "$APP"; fi
echo "Standalone MapRemote.app built for $(uname -m)."
