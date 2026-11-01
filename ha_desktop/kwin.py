"""KDE Plasma op Wayland: een venster als tray-popup neerzetten via een KWin-script.

Een Wayland-app mag zijn eigen vensters niet positioneren, maar een KWin-script
wel (kdotool gebruikt dezelfde aanpak). Het script blijft geladen zolang de app
draait: elke keer dat het paneel verschijnt (op Wayland is dat voor KWin een nieuw
venster) zet het dat bij de muis tegen het paneel aan, boven alles en uit de taakbalk.

QtDBus wordt pas geladen als het nodig is; op andere desktops hoeft het niet
geïnstalleerd te zijn.
"""

from __future__ import annotations

import json
import logging
import os

from ha_desktop.config import cache_dir

log = logging.getLogger(__name__)

PLUGIN = "ha-desktop-panel"
GAP = 8

# KWin 6-scripting-API. __CAPTION__, __PID__ en __GAP__ worden ingevuld.
SCRIPT = """
const CAPTION = __CAPTION__, PID = __PID__, GAP = __GAP__;

function place(window) {
    if (window.caption !== CAPTION || window.pid !== PID) {
        return;
    }
    const cursor = workspace.cursorPos;
    const output = workspace.screenAt(cursor) || workspace.activeScreen;
    const area = workspace.clientArea(KWin.PlacementArea, output, workspace.currentDesktop);
    const bottom = cursor.y > area.y + area.height / 2;
    // Tegen het paneel aan aan de kant waar de muis is, horizontaal gecentreerd op de muis.
    // Groeit het venster later (tegels geladen), dan blijft het tegen het paneel staan.
    function fit() {
        const geo = window.frameGeometry;
        const x = Math.round(Math.max(area.x + GAP,
                                      Math.min(cursor.x - geo.width / 2, area.x + area.width - geo.width - GAP)));
        const y = Math.round(bottom ? area.y + area.height - geo.height - GAP : area.y + GAP);
        if (geo.x !== x || geo.y !== y) {
            window.frameGeometry = {x: x, y: y, width: geo.width, height: geo.height};
        }
    }
    fit();
    window.frameGeometryChanged.connect(fit);
    window.noBorder = true;
    window.keepAbove = true;
    window.skipTaskbar = true;
    window.skipSwitcher = true;
    window.skipPager = true;
    workspace.activeWindow = window;
}

workspace.windowList().forEach(place);
workspace.windowAdded.connect(place);
"""

_loaded = False


def is_kde() -> bool:
    return "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper().split(":")


def is_plasma6() -> bool:
    """Het script gebruikt de API van KWin 6; Plasma 5 kent die niet."""
    version = os.environ.get("KDE_SESSION_VERSION", "")
    return is_kde() and version.isdigit() and int(version) >= 6


def _call(method: str, *args) -> list | None:
    from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage

    msg = QDBusMessage.createMethodCall("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", method)
    if args:
        msg.setArguments(list(args))
    reply = QDBusConnection.sessionBus().call(msg, QDBus.CallMode.Block, 2000)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        log.info("KWin %s mislukt: %s", method, reply.errorMessage())
        return None
    return reply.arguments()


def available() -> bool:
    """Draaien we onder KWin 6 met scripting via DBus?"""
    if not is_plasma6():
        return False
    try:
        from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage
    except ImportError:
        return False
    if not QDBusConnection.sessionBus().isConnected():
        return False
    msg = QDBusMessage.createMethodCall("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                        "org.freedesktop.DBus", "NameHasOwner")
    msg.setArguments(["org.kde.KWin"])
    reply = QDBusConnection.sessionBus().call(msg, QDBus.CallMode.Block, 2000)
    return reply.type() == QDBusMessage.MessageType.ReplyMessage and bool(reply.arguments()[0])


def script(caption: str) -> str:
    return (SCRIPT.replace("__CAPTION__", json.dumps(caption)).replace("__PID__", str(os.getpid()))
            .replace("__GAP__", str(GAP)))


def place(caption: str) -> bool:
    """Zorg dat KWin het venster met deze titel bij de muis zet, nu en elke keer dat het verschijnt."""
    global _loaded
    if _loaded and _call("isScriptLoaded", PLUGIN) == [True]:
        return True  # draait al (na een herstart van KWin niet meer: dan opnieuw laden)
    path = cache_dir() / "kwin-panel.js"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(script(caption), encoding="utf-8")
    except OSError as exc:
        log.warning("KWin-script niet opgeslagen: %s", exc)
        return False
    _call("unloadScript", PLUGIN)  # van een vorige keer (ander proces-ID)
    loaded = _call("loadScript", str(path), PLUGIN)
    if not loaded or loaded[0] < 0:
        return False
    _loaded = _call("start") is not None
    return _loaded


def unload() -> None:
    global _loaded
    if _loaded:
        _call("unloadScript", PLUGIN)
        _loaded = False
