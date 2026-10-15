#!/bin/bash
# Builds Dossiary.app, a launcher that opens the dossiary.html next to it in
# Chrome (or Edge), with dossiary.html's own favicon as its icon.
# Usage: packaging/macos/build-launcher.sh [destination folder]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
BUILD="$HERE/build"
APP="$BUILD/Dossiary.app"

rm -rf "$BUILD"
mkdir -p "$BUILD/icon.iconset"
osacompile -o "$APP" "$HERE/Dossiary.applescript"

# Icon: the SVG favicon embedded in dossiary.html
python3 - "$REPO_ROOT/dossiary.html" "$BUILD/favicon.svg" <<'PY'
import re, sys, urllib.parse
html = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r'rel="icon" type="image/svg\+xml" href="data:image/svg\+xml,([^"]+)"', html)
if not m:
    sys.exit("build-launcher: no SVG favicon found in dossiary.html")
open(sys.argv[2], "w", encoding="utf-8").write(urllib.parse.unquote(m.group(1)))
PY
qlmanage -t -s 1024 -o "$BUILD" "$BUILD/favicon.svg" > /dev/null 2>&1
[ -f "$BUILD/favicon.svg.png" ] || { echo "build-launcher: qlmanage did not render the icon" >&2; exit 1; }
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$BUILD/favicon.svg.png" --out "$BUILD/icon.iconset/icon_${size}x${size}.png" > /dev/null
  sips -z $((size * 2)) $((size * 2)) "$BUILD/favicon.svg.png" --out "$BUILD/icon.iconset/icon_${size}x${size}@2x.png" > /dev/null
done
iconutil -c icns -o "$APP/Contents/Resources/applet.icns" "$BUILD/icon.iconset"
# osacompile's Assets.car carries the default script icon and wins over applet.icns
rm -f "$APP/Contents/Resources/Assets.car"
plutil -remove CFBundleIconName "$APP/Contents/Info.plist" 2>/dev/null || true
plutil -replace CFBundleIdentifier -string "io.github.aarneaarebye.dossiary.launcher" "$APP/Contents/Info.plist"

codesign --force --deep -s - "$APP"
echo "Built $APP"

if [ $# -ge 1 ]; then
  DEST="$1"
  mkdir -p "$DEST"
  rm -rf "$DEST/Dossiary.app"
  ditto "$APP" "$DEST/Dossiary.app"
  touch "$DEST/Dossiary.app"  # so Finder picks up the new icon
  echo "Copied to $DEST/Dossiary.app"
fi
