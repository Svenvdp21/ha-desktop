#!/usr/bin/env bash
# Maakt een AppImage uit de PyInstaller-build in dist/ha-desktop.
# Resultaat: dist/HomeAssistantDesktop-<versie>-x86_64.AppImage
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="$(python3 -c "import sys; sys.path.insert(0, '$ROOT'); import ha_desktop; print(ha_desktop.__version__)")"
APP_ID=com.nordicnode.HADesktop
WORK="$(mktemp -d)"
APPDIR="$WORK/AppDir"

mkdir -p "$APPDIR/usr/lib"
cp -a "$ROOT/dist/ha-desktop" "$APPDIR/usr/lib/ha-desktop"
cp "$ROOT/data/$APP_ID.desktop" "$APPDIR/"
cp "$ROOT/build/icon.png" "$APPDIR/$APP_ID.png"
ln -s "$APP_ID.png" "$APPDIR/.DirIcon"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/ha-desktop/ha-desktop" "$@"
EOF
chmod 755 "$APPDIR/AppRun"

TOOL="$WORK/appimagetool"
curl -fsSL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x "$TOOL"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" \
    "$ROOT/dist/HomeAssistantDesktop-$VERSION-x86_64.AppImage"
rm -rf "$WORK"
ls -1 "$ROOT"/dist/*.AppImage
