#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:?Usage: build-icon.sh /path/to/MapRemote.icns}"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
mkdir "$TEMP/MapRemote.iconset"
for size in 16 32 128 256 512; do
  /usr/bin/sips -z "$size" "$size" "$ROOT/assets/icon.png" --out "$TEMP/MapRemote.iconset/icon_${size}x${size}.png" >/dev/null
  double=$((size*2))
  /usr/bin/sips -z "$double" "$double" "$ROOT/assets/icon.png" --out "$TEMP/MapRemote.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
/usr/bin/iconutil -c icns "$TEMP/MapRemote.iconset" -o "$OUT"
