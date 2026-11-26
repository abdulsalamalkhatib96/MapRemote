#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
if [[ "$(uname -s)" != Darwin ]]; then echo 'This app builds on macOS only.'; exit 1; fi
if ! /usr/bin/xcode-select -p >/dev/null 2>&1; then
  /usr/bin/xcode-select --install || true
  echo 'Install Apple Command Line Tools, then run Build.command again.'; read -r -p 'Press Enter to close.'; exit 1
fi
if ! command -v python3 >/dev/null; then echo 'Install Python 3: brew install python'; read -r; exit 1; fi
if [[ "${MAPREMOTE_BUILD_ONLY:-0}" != 1 ]] && ! command -v mitmdump >/dev/null && [[ ! -x /Applications/mitmproxy.app/Contents/MacOS/mitmdump ]]; then
  if command -v brew >/dev/null; then brew install --cask mitmproxy; else echo 'Install mitmproxy from https://mitmproxy.org or Homebrew, then retry.'; read -r; exit 1; fi
fi
APP="$PWD/MapRemote.app"
TMP="$(mktemp -d "$PWD/.build.XXXXXXXX")"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/MapRemote.app/Contents/MacOS" "$TMP/MapRemote.app/Contents/Resources"
CONTENTS="$TMP/MapRemote.app/Contents"
/usr/bin/xcrun swiftc -swift-version 5 -O -framework SystemConfiguration ProxyHelper.swift -o "$CONTENTS/Resources/ProxyHelper"
/usr/bin/xcrun swiftc -swift-version 5 -O -framework AppKit -framework WebKit NativeApp.swift -o "$CONTENTS/MacOS/MapRemote"
cp app.py addon.py rules.py system_proxy.py index.html "$CONTENTS/Resources/"
cp Info.plist "$CONTENTS/Info.plist"
bash scripts/build-icon.sh "$CONTENTS/Resources/MapRemote.icns"
/usr/bin/codesign --force --sign - "$CONTENTS/Resources/ProxyHelper"
/usr/bin/codesign --force --sign - "$TMP/MapRemote.app"
if [[ -e "$APP" ]]; then echo 'Existing MapRemote.app found. Close it and remove it before rebuilding.'; exit 1; fi
mv "$TMP/MapRemote.app" "$APP"
if [[ "${MAPREMOTE_BUILD_ONLY:-0}" != 1 ]]; then /usr/bin/open "$APP"; fi
echo 'MapRemote.app built. Open it from Finder next time.'
