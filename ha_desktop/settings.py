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
from ha_desktop.i18n import N_, _
from ha_desktop.onboarding import DEVICE_HELP, TOKEN_HELP, TokenForm, _wrap

STATE_TEXT = {
    "connected": ("#2a2", N_("● Connected — notifications are coming in")),
    "connecting": ("", N_("● Connecting…")),
    "disconnected": ("#c80", N_("● Not connected")),
    "error": ("#d33", N_("● Error")),
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
        self.setWindowTitle(_("Settings — {app}").format(app=APP_NAME))
        self.setMinimumWidth(520)
        self.config, self.tokens, self.push = config, tokens, push
        layout = QVBoxLayout(self)

        # Server
        server = QGroupBox(_("Server"))
        row = QHBoxLayout(server)
        row.addWidget(QLabel(f"<b>{config.server_url}</b>"), 1)
        change = QPushButton(_("Change server…"))
        change.clicked.connect(self._change_server)
        row.addWidget(change)
        layout.addWidget(server)

        # Meldingen
        notify = QGroupBox(_("Notifications"))
        col = QVBoxLayout(notify)
        self.notify_enabled = QCheckBox(_("Show notifications from Home Assistant"))
        self.notify_enabled.setChecked(config.notifications)
        col.addWidget(self.notify_enabled)
        self.status = _wrap("")
        col.addWidget(self.status)
        col.addWidget(_wrap(_(TOKEN_HELP)))
        col.addWidget(_wrap(_(DEVICE_HELP)))
        make_token = QPushButton(_("Create token in Home Assistant…"))
        make_token.clicked.connect(self._open_token_page)
        col.addWidget(make_token)
        self.token_form = TokenForm(config, api, tokens)
        if tokens.get(config.server_url):
            self.token_form.token.setPlaceholderText(_("A token is saved — leave empty to keep it"))
        self.token_form.registered.connect(self._registered)
        col.addWidget(self.token_form)
        layout.addWidget(notify)
        self.notify_enabled.toggled.connect(self.token_form.setEnabled)
        self.notify_enabled.toggled.connect(lambda _: self._show_status())
        self.token_form.setEnabled(config.notifications)

        # Venster
        window = QGroupBox(_("Window"))
        col = QVBoxLayout(window)
        self.close_to_tray = QCheckBox(_("Keep running in the background when closed (system tray)"))
        self.close_to_tray.setChecked(config.close_to_tray and tray_available)
        self.close_to_tray.setEnabled(tray_available)
        if not tray_available:
            self.close_to_tray.setToolTip(_("Your desktop has no system tray."))
        self.autostart = QCheckBox(_("Start at login (hidden)"))
        self.autostart.setChecked(autostart_file().exists())
        col.addWidget(self.close_to_tray)
        col.addWidget(self.autostart)
        layout.addWidget(window)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(_("Save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(_("Cancel"))
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
            self.status.setText(_("Off."))
            return
        if not self.config.notifications:
            self.status.setText(_("Not active yet — paste a token below and choose <b>Save</b>."))
            return
        state, detail = state or self.push.state, detail or self.push.detail
        color, text = STATE_TEXT.get(state, ("", state))
        text = f"<span style='color:{color}'>{_(text)}</span>" if color else _(text)
        self.status.setText(text + (f"<br><small>{detail}</small>" if detail else ""))

    def _open_token_page(self) -> None:
        self.open_path.emit("/profile/security")
        self.reject()

    def _change_server(self) -> None:
        answer = QMessageBox.question(
            self, _("Change server"),
            _("Do you want to connect to a different Home Assistant server? You will go through the "
              "first-time setup again."),
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
