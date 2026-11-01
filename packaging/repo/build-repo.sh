#!/usr/bin/env bash
# Bouwt een ondertekende dnf-repo uit de RPM's in <rpm-map> naar <uitvoermap>.
# De ondertekensleutel moet al in gpg geïmporteerd zijn.
# Gebruik: build-repo.sh <rpm-map> <uitvoermap>
set -euo pipefail

SRC="$1"
OUT="$2"
HERE="$(cd "$(dirname "$0")" && pwd)"
KEY_ID=8EA3A1F21D6D751D4A4B4E57555E1BD839470668
BASE_URL=https://svenvdp21.github.io/ha-desktop

mkdir -p "$OUT/rpm"
cp "$SRC"/*.rpm "$OUT/rpm/"
rpm --define "_gpg_name $KEY_ID" \
    --define "_gpg_sign_cmd_extra_args --batch --pinentry-mode loopback" \
    --addsign "$OUT"/rpm/*.rpm
createrepo_c --quiet "$OUT/rpm"
gpg --batch --yes --pinentry-mode loopback --local-user "$KEY_ID" \
    --detach-sign --armor "$OUT/rpm/repodata/repomd.xml"

cp "$HERE/ha-desktop.gpg" "$OUT/"
cat > "$OUT/ha-desktop.repo" <<EOF
[ha-desktop]
name=Home Assistant Desktop (unofficial)
baseurl=$BASE_URL/rpm/
enabled=1
gpgcheck=1
repo_gpgcheck=1
gpgkey=$BASE_URL/ha-desktop.gpg
EOF

cat > "$OUT/index.html" <<EOF
<!doctype html>
<meta charset="utf-8">
<title>Home Assistant Desktop — dnf repo</title>
<h1>Home Assistant Desktop (unofficial) — dnf repo</h1>
<pre>sudo dnf config-manager addrepo --from-repofile=$BASE_URL/ha-desktop.repo
sudo dnf install ha-desktop</pre>
<p><a href="https://github.com/Svenvdp21/ha-desktop">github.com/Svenvdp21/ha-desktop</a></p>
EOF
ls -R "$OUT" | head -20
