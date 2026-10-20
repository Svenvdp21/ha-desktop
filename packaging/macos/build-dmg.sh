#!/usr/bin/env bash
# Maakt een .dmg uit "dist/Home Assistant Desktop.app".
# Gebruik: build-dmg.sh <arm64|x86_64>
set -euo pipefail

ARCH="$1"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="$(python3 -c "import sys; sys.path.insert(0, '$ROOT'); import ha_desktop; print(ha_desktop.__version__)")"
STAGE="$(mktemp -d)"

cp -R "$ROOT/dist/Home Assistant Desktop.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Home Assistant Desktop" -srcfolder "$STAGE" -ov -format UDZO \
    "$ROOT/dist/HomeAssistantDesktop-$VERSION-macos-$ARCH.dmg"
rm -rf "$STAGE"
ls -1 "$ROOT"/dist/*.dmg
