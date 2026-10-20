#!/usr/bin/env bash
# Bouwt het RPM-pakket. Resultaat: dist/ha-desktop-<versie>-1.<distro>.noarch.rpm
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(python3 -c "import sys; sys.path.insert(0, '$ROOT'); import ha_desktop; print(ha_desktop.__version__)")"
# rpmbuild kan niet goed met spaties in paden; bouw daarom in een tijdelijke map.
TOP="$(mktemp -d)"
trap 'rm -rf "$TOP"' EXIT
NAME="ha-desktop-$VERSION"

mkdir -p "$TOP"/{SOURCES,SPECS} "$ROOT/dist"

tar -czf "$TOP/SOURCES/$NAME.tar.gz" -C "$ROOT" \
    --exclude=__pycache__ --transform "s|^|$NAME/|" \
    ha_desktop data README.md README.en.md LICENSE

rpmbuild -bb "$ROOT/packaging/ha-desktop.spec" \
    --define "_topdir $TOP" \
    --define "app_version $VERSION"

cp "$TOP"/RPMS/noarch/*.rpm "$ROOT/dist/"
ls -1 "$ROOT"/dist/*.rpm
