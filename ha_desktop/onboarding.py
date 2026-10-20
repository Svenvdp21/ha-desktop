"""Eerste-keer-instellen: serveradres kiezen en (optioneel) meldingen aanzetten."""

from __future__ import annotations

import shiboken6
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ha_desktop import APP_NAME
from ha_desktop.config import Config, normalize_url
from ha_desktop.haapi import HaApi, Result
from ha_desktop.i18n import N_, _
from ha_desktop.resources import app_icon

TOKEN_HELP = N_(
    "Notifications use a <b>long-lived access token</b>. Create one in Home Assistant via "
    "<i>your profile → Security → Long-lived access tokens → Create token</i> (at the bottom "
    "of the page) and paste it below."
)
DEVICE_HELP = N_(
    "This computer then shows up in Home Assistant as a device, and you can send notifications "
    "with the action <code>notify.mobile_app_&lt;name&gt;</code>."
)


def ask_trust_certificate(parent: QWidget, host: str) -> bool:
    answer = QMessageBox.warning(
        parent,
        _("Unknown certificate"),
        _("The security certificate of <b>{host}</b> is not trusted (for example because it is "
          "self-signed).<br><br>Only trust it if this is your own server. Connect anyway?").format(host=host),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def _card(*widgets: QWidget) -> QWidget:
    """Gecentreerde kolom met vaste maximale breedte."""
    outer = QWidget()
    row = QHBoxLayout(outer)
    row.addStretch(1)
    inner = QFrame()
    inner.setMaximumWidth(460)
    col = QVBoxLayout(inner)
    col.addStretch(1)
    for w in widgets:
        col.addWidget(w)
    col.addStretch(2)
    row.addWidget(inner, 4)
    row.addStretch(1)
    return outer


def _title(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setPointSizeF(font.pointSizeF() * 1.6)
    font.setBold(True)
    label.setFont(font)
    return label


def _wrap(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    return label


class TokenForm(QWidget):
    """Token invoeren + apparaat registreren. Gedeeld door onboarding en instellingen."""

    registered = Signal()

    def __init__(self, config: Config, api: HaApi, tokens, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config, self.api, self.tokens = config, api, tokens
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.token = QLineEdit(placeholderText=_("Paste your token here"))
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.device = QLineEdit(config.device_name, placeholderText=_("Name of this computer"))
        self.status = _wrap("")
        self.status.hide()
        self.busy = QProgressBar(maximum=0, textVisible=False, maximumHeight=6)
        self.busy.hide()
        layout.addWidget(QLabel(_("Access token")))
        layout.addWidget(self.token)
        layout.addWidget(QLabel(_("Device name in Home Assistant")))
        layout.addWidget(self.device)
        layout.addWidget(self.busy)
        layout.addWidget(self.status)

    def submit(self) -> None:
        token = self.token.text().strip() or self.tokens.get(self.config.server_url)
        if not token:
            self._error(_("Enter a token first."))
            return
        name = self.device.text().strip()
        if not name:
            self._error(_("Give this computer a name."))
            return
        if name != self.config.device_name or token != self.tokens.get(self.config.server_url):
            # Nieuwe naam of nieuw token: opnieuw registreren.
            self.config.webhook_id = ""
        self.config.device_name = name
        if self.config.is_registered:
            self.config.notifications = True
            self.config.save()
            self.registered.emit()
            return
        self.setEnabled(False)
        self.busy.show()
        self.status.hide()
        self.api.register_device(self.config.server_url, token, lambda r: self._done(r, token))

    def _done(self, result: Result, token: str) -> None:
        if not shiboken6.isValid(self):
            return  # venster is intussen gesloten
        self.setEnabled(True)
        self.busy.hide()
        if not result.ok:
            self._error(result.error)
            return
        self.tokens.set(self.config.server_url, token)
        self.config.webhook_id = result.data["webhook_id"]
        self.config.registered_for = self.config.server_url
        self.config.notifications = True
        self.config.notif_prompt_dismissed = True
        self.config.save()
        self.token.clear()
        self.registered.emit()

    def _error(self, text: str) -> None:
        self.status.setText(f"<span style='color:#d33'>{text}</span>")
        self.status.show()


class Onboarding(QWidget):
    finished = Signal()

    def __init__(self, config: Config, api: HaApi, tokens, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config, self.api, self.tokens = config, api, tokens
        self._candidates: list[str] = []
        self.stack = QStackedWidget()
        QVBoxLayout(self).addWidget(self.stack)
        self.stack.addWidget(self._server_page())
        self.stack.addWidget(self._notify_page())

    def restart(self) -> None:
        self.url.setText(self.config.server_url or "")
        self.stack.setCurrentIndex(0)
        self.url.setFocus()

    # -- stap 1: server ------------------------------------------------------

    def _server_page(self) -> QWidget:
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(72, 72))
        self.url = QLineEdit(placeholderText="http://homeassistant.local:8123")
        self.url.returnPressed.connect(self._connect)
        self.connect_btn = QPushButton(_("Connect"))
        self.connect_btn.setDefault(True)
        self.connect_btn.clicked.connect(self._connect)
        self.server_busy = QProgressBar(maximum=0, textVisible=False, maximumHeight=6)
        self.server_busy.hide()
        self.server_status = _wrap("")
        self.server_status.hide()
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.connect_btn)
        row = QWidget()
        row.setLayout(buttons)
        return _card(
            logo,
            _title(_("Welcome to {app}").format(app=APP_NAME)),
            _wrap(_("Enter the address of your Home Assistant server. This is usually "
                    "<code>http://homeassistant.local:8123</code>, your server's IP address with port 8123, "
                    "or your external address (e.g. Home Assistant Link).")),
            QLabel(_("Server address")),
            self.url,
            self.server_busy,
            self.server_status,
            row,
        )

    def _connect(self) -> None:
        try:
            self._candidates = normalize_url(self.url.text() or self.url.placeholderText())
        except ValueError as exc:
            self._server_error(str(exc))
            return
        self.connect_btn.setEnabled(False)
        self.url.setEnabled(False)
        self.server_busy.show()
        self.server_status.hide()
        self._first_error = ""
        self._try_next()

    def _try_next(self) -> None:
        url = self._candidates.pop(0)
        self.api.probe(url, lambda result: self._probed(url, result))

    def _probed(self, url: str, result: Result) -> None:
        if result.ok:
            self._reset_server_form()
            if url != self.config.server_url:
                self.config.webhook_id = ""
                self.config.notifications = False
                self.config.notif_prompt_dismissed = False
            self.config.server_url = url
            self.config.save()
            self.stack.setCurrentIndex(1)
            self.token_form.token.setFocus()
            return
        if result.cert_host:
            if ask_trust_certificate(self, result.cert_host):
                self.config.trust_host(result.cert_host)
                self._candidates.insert(0, url)
                self._try_next()
                return
        self._first_error = self._first_error or result.error
        if self._candidates:
            self._try_next()
        else:
            self._reset_server_form()
            self._server_error(self._first_error)

    def _reset_server_form(self) -> None:
        self.connect_btn.setEnabled(True)
        self.url.setEnabled(True)
        self.server_busy.hide()

    def _server_error(self, text: str) -> None:
        self.server_status.setText(f"<span style='color:#d33'>{text}</span>")
        self.server_status.show()

    # -- stap 2: meldingen (optioneel) ---------------------------------------

    def _notify_page(self) -> QWidget:
        self.token_form = TokenForm(self.config, self.api, self.tokens)
        self.token_form.registered.connect(self.finished)
        self.token_form.token.returnPressed.connect(self.token_form.submit)
        skip = QPushButton(_("Skip"))
        skip.clicked.connect(self._skip)
        enable = QPushButton(_("Enable notifications"))
        enable.setDefault(True)
        enable.clicked.connect(self.token_form.submit)
        buttons = QHBoxLayout()
        buttons.addWidget(skip)
        buttons.addStretch(1)
        buttons.addWidget(enable)
        row = QWidget()
        row.setLayout(buttons)
        return _card(
            _title(_("Get notifications?")),
            _wrap(_(TOKEN_HELP)),
            _wrap(_(DEVICE_HELP)),
            _wrap(_("<i>No token yet? Choose Skip, log in first and turn on notifications later in "
                    "Settings (Ctrl+,).</i>")),
            self.token_form,
            row,
        )

    def _skip(self) -> None:
        self.config.save()
        self.finished.emit()
