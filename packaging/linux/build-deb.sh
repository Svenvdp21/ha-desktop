#!/usr/bin/env bash
# Maakt een .deb uit de PyInstaller-build in dist/ha-desktop.
# Resultaat: dist/ha-desktop_<versie>_amd64.deb
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="$(python3 -c "import sys; sys.path.insert(0, '$ROOT'); import ha_desktop; print(ha_desktop.__version__)")"
APP_ID=com.nordicnode.HADesktop
PKG="$(mktemp -d)/ha-desktop"

mkdir -p "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/scalable/apps" "$PKG/usr/share/doc/ha-desktop"
cp -a "$ROOT/dist/ha-desktop" "$PKG/opt/ha-desktop"
ln -s /opt/ha-desktop/ha-desktop "$PKG/usr/bin/ha-desktop"
cp "$ROOT/data/$APP_ID.desktop" "$PKG/usr/share/applications/"
cp "$ROOT/ha_desktop/data/$APP_ID.svg" "$PKG/usr/share/icons/hicolor/scalable/apps/"
cp "$ROOT/LICENSE" "$PKG/usr/share/doc/ha-desktop/copyright"

cat > "$PKG/DEBIAN/control" <<EOF
Package: ha-desktop
Version: $VERSION
Architecture: amd64
Maintainer: Svenvdp21 <177861668+Svenvdp21@users.noreply.github.com>
Installed-Size: $(du -sk "$PKG" | cut -f1)
Depends: libc6 (>= 2.35), libnss3, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libegl1, libgl1, libgbm1, libfontconfig1, libdbus-1-3, libwayland-client0, libwayland-server0, libwayland-cursor0, libwayland-egl1
Recommends: libnotify-bin, gnome-keyring | kwalletmanager
Section: utils
Priority: optional
Homepage: https://github.com/Svenvdp21/ha-desktop
Description: Unofficial Home Assistant desktop app with notifications
 The Home Assistant web interface in its own window, with first-run setup,
 system tray and desktop notifications via the Mobile App integration.
 Not affiliated with Home Assistant or the Open Home Foundation.
EOF

cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q /usr/share/icons/hicolor || true
EOF
chmod 755 "$PKG/DEBIAN/postinst"

dpkg-deb --build --root-owner-group "$PKG" "$ROOT/dist/ha-desktop_${VERSION}_amd64.deb"
rm -rf "$(dirname "$PKG")"
ls -1 "$ROOT"/dist/*.deb
