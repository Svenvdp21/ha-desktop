"""Toont bureaubladmeldingen.

Voorkeur: notify-send (libnotify) met een "Openen"-actie, werkt op KDE, GNOME en
andere desktops. Valt terug op een ballonmelding van het tray-icoon.
"""

from __future__ import annotations

import shutil

from PySide6.QtCore import QObject, QProcess, Signal
from PySide6.QtWidgets import QSystemTrayIcon

from ha_desktop import APP_ID, APP_NAME
from ha_desktop.i18n import _
from ha_desktop.resources import icon_path


class Notifier(QObject):
    # Pad of URL om te openen nadat de gebruiker op de melding klikte ("" = startpagina).
    clicked = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._notify_send = shutil.which("notify-send")
        self.tray: QSystemTrayIcon | None = None
        self._tray_target = ""
        self._procs: set[QProcess] = set()

    def set_tray(self, tray: QSystemTrayIcon | None) -> None:
        self.tray = tray
        if tray:
            tray.messageClicked.connect(lambda: self.clicked.emit(self._tray_target))

    def show(self, title: str, message: str, target: str = "") -> None:
        title = title or APP_NAME
        if self._notify_send:
            proc = QProcess(self)
            proc.setProgram(self._notify_send)
            proc.setArguments([
                "--app-name", APP_NAME,
                "--icon", str(icon_path()),
                "--hint", f"string:desktop-entry:{APP_ID}",
                "--action", f"default={_('Open')}",
                "--", title, message,
            ])

            def finished(*_: object, proc: QProcess = proc) -> None:
                out = bytes(proc.readAllStandardOutput().data()).decode(errors="ignore").strip()
                self._procs.discard(proc)
                proc.deleteLater()
                if out == "default":
                    self.clicked.emit(target)

            proc.finished.connect(finished)
            self._procs.add(proc)
            proc.start()
        elif self.tray and self.tray.isVisible():
            self._tray_target = target
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 10_000)

    def close_all(self) -> None:
        for proc in list(self._procs):
            proc.finished.disconnect()
            proc.kill()
            proc.waitForFinished(500)
        self._procs.clear()


def notification_target(event: dict) -> str:
    """Haal het klikdoel uit een HA-notificatie (zelfde velden als de mobiele apps)."""
    data = event.get("data") or {}
    if not isinstance(data, dict):
        return ""
    return str(data.get("url") or data.get("clickAction") or "")
