#!/usr/bin/env bash
# Installeert de Home Assistant-app voor de huidige gebruiker (geen root nodig).
# Gebruik: ./install.sh            installeren
#          ./install.sh --remove   verwijderen (instellingen en login blijven bewaard)
set -euo pipefail

APP_ID=com.nordicnode.HADesktop
SRC="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin/ha-desktop"
DESKTOP="${XDG_DATA_HOME:-$HOME/.local/share}/applications/$APP_ID.desktop"
ICON="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/$APP_ID.svg"

if [[ "${1:-}" == "--remove" ]]; then
    rm -f "$BIN" "$DESKTOP" "$ICON" "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/$APP_ID.desktop"
    echo "Home Assistant-app verwijderd. Instellingen staan nog in ~/.config/ha-desktop en ~/.local/share/ha-desktop."
    exit 0
fi

if ! python3 -c "import PySide6.QtWebEngineWidgets, PySide6.QtWebSockets" 2>/dev/null; then
    echo "PySide6 met QtWebEngine ontbreekt. Installeer het met:"
    echo "  sudo dnf install python3-pyside6"
    exit 1
fi

mkdir -p "$(dirname "$BIN")" "$(dirname "$DESKTOP")" "$(dirname "$ICON")"

cat > "$BIN" <<EOF
#!/bin/sh
PYTHONPATH="$SRC\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m ha_desktop "\$@"
EOF
chmod +x "$BIN"

install -m 644 "$SRC/ha_desktop/data/$APP_ID.svg" "$ICON"
sed "s|^Exec=.*|Exec=$BIN %U|" "$SRC/data/$APP_ID.desktop" > "$DESKTOP"

update-desktop-database "$(dirname "$DESKTOP")" 2>/dev/null || true
gtk-update-icon-cache -q "$(dirname "$(dirname "$(dirname "$ICON")")")" 2>/dev/null || true

echo "Geïnstalleerd. Start 'Home Assistant' vanuit het menu of met: ha-desktop"
