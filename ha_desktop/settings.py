"""Instellingenvenster."""

from __future__ import annotations

import shlex
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ha_desktop import APP_ID, APP_NAME
from ha_desktop.config import Config, _xdg
from ha_desktop.onboarding import DEVICE_HELP, TOKEN_HELP, TokenForm, _wrap

STATE_TEXT = {
    "connected": "<span style='color:#2a2'>● Verbonden — meldingen komen binnen</span>",
    "connecting": "● Verbinden…",
    "disconnected": "<span style='color:#c80'>● Niet verbonden</span>",
    "error": "<span style='color:#d33'>● Fout</span>",
}


def autostart_file() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / "autostart" / f"{APP_ID}.desktop"


def launch_command() -> str:
    installed = shutil.which("ha-desktop")
    if installed:
        return installed
    package_root = Path(__file__).resolve().parent.parent
    return f"env PYTHONPATH={shlex.quote(str(package_root))} {sys.executable} -m ha_desktop"


def set_autostart(enabled: bool) -> None:
    path = autostart_file()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        f"Exec={launch_command()} --hidden\n"
        f"Icon={APP_ID}\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


class SettingsDialog(QDialog):
    change_server = Signal()
    open_path = Signal(str)
    notifications_changed = Signal()

    def __init__(self, config: Config, api, tokens, push, tray_available: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Instellingen — {APP_NAME}")
        self.setMinimumWidth(520)
        self.config, self.tokens, self.push = config, tokens, push
        layout = QVBoxLayout(self)

        # Server
        server = QGroupBox("Server")
        row = QHBoxLayout(server)
        row.addWidget(QLabel(f"<b>{config.server_url}</b>"), 1)
        change = QPushButton("Andere server…")
        change.clicked.connect(self._change_server)
        row.addWidget(change)
        layout.addWidget(server)

        # Meldingen
        notify = QGroupBox("Meldingen")
        col = QVBoxLayout(notify)
        self.notify_enabled = QCheckBox("Meldingen van Home Assistant tonen")
        self.notify_enabled.setChecked(config.notifications)
        col.addWidget(self.notify_enabled)
        self.status = _wrap("")
        col.addWidget(self.status)
        col.addWidget(_wrap(TOKEN_HELP))
        col.addWidget(_wrap(DEVICE_HELP))
        make_token = QPushButton("Token aanmaken in Home Assistant…")
        make_token.clicked.connect(self._open_token_page)
        col.addWidget(make_token)
        self.token_form = TokenForm(config, api, tokens)
        if tokens.get(config.server_url):
            self.token_form.token.setPlaceholderText("Er is een token opgeslagen — laat leeg om te behouden")
        self.token_form.registered.connect(self._registered)
        col.addWidget(self.token_form)
        layout.addWidget(notify)
        self.notify_enabled.toggled.connect(self.token_form.setEnabled)
        self.notify_enabled.toggled.connect(lambda _: self._show_status())
        self.token_form.setEnabled(config.notifications)

        # Venster
        window = QGroupBox("Venster")
        col = QVBoxLayout(window)
        self.close_to_tray = QCheckBox("Bij sluiten op de achtergrond blijven draaien (systeemvak)")
        self.close_to_tray.setChecked(config.close_to_tray and tray_available)
        self.close_to_tray.setEnabled(tray_available)
        if not tray_available:
            self.close_to_tray.setToolTip("Je bureaublad heeft geen systeemvak.")
        self.autostart = QCheckBox("Starten bij inloggen (verborgen)")
        self.autostart.setChecked(autostart_file().exists())
        col.addWidget(self.close_to_tray)
        col.addWidget(self.autostart)
        layout.addWidget(window)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Opslaan")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuleren")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        push.status_changed.connect(self._show_status)
        self._show_status(push.state, push.detail)

    def showEvent(self, event) -> None:
        # Hoogte afstemmen op de omgebroken teksten bij deze breedte.
        super().showEvent(event)
        height = self.layout().totalHeightForWidth(self.width())
        if height > self.height():
            self.resize(self.width(), height)

    def _show_status(self, state: str = "", detail: str = "") -> None:
        if not self.notify_enabled.isChecked():
            self.status.setText("Uitgeschakeld.")
            return
        if not self.config.notifications:
            self.status.setText("Nog niet actief — plak hieronder een token en kies <b>Opslaan</b>.")
            return
        state, detail = state or self.push.state, detail or self.push.detail
        self.status.setText(STATE_TEXT.get(state, state) + (f"<br><small>{detail}</small>" if detail else ""))

    def _open_token_page(self) -> None:
        self.open_path.emit("/profile/security")
        self.reject()

    def _change_server(self) -> None:
        answer = QMessageBox.question(
            self, "Andere server",
            "Wil je verbinden met een andere Home Assistant-server? "
            "Je gaat dan opnieuw door de eerste-keer-instellingen.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.reject()
            self.change_server.emit()

    def _save(self) -> None:
        self.config.close_to_tray = self.close_to_tray.isChecked()
        set_autostart(self.autostart.isChecked())
        if self.notify_enabled.isChecked():
            # TokenForm registreert indien nodig; _registered sluit daarna het venster.
            self.token_form.submit()
            return
        if self.config.notifications:
            self.config.notifications = False
            self.notifications_changed.emit()
        self.config.save()
        self.accept()

    def _registered(self) -> None:
        self.notifications_changed.emit()
        self.accept()

    def done(self, result: int) -> None:
        try:
            self.push.status_changed.disconnect(self._show_status)
        except RuntimeError:
            pass
        super().done(result)
