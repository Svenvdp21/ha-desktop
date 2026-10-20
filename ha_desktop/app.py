"""Hoofdvenster, systeemvak en het samenvoegen van alle onderdelen."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QTimer, QTranslator, Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from ha_desktop import APP_ID, APP_NAME, __version__
from ha_desktop.config import Config, TokenStore
from ha_desktop.haapi import HaApi
from ha_desktop.i18n import _, language
from ha_desktop.notifier import Notifier, notification_target
from ha_desktop.onboarding import Onboarding, _card, _title, _wrap
from ha_desktop.push import PushClient
from ha_desktop.resources import app_icon
from ha_desktop.settings import SettingsDialog
from ha_desktop.webview import HaView, make_profile

log = logging.getLogger(__name__)

RETRY_SECONDS = 10
INSTANCE_KEY = f"{APP_ID}-{getpass.getuser()}"


class ErrorPage(QWidget):
    """Wordt getoond als de server onbereikbaar is; probeert automatisch opnieuw."""

    def __init__(self, retry, settings, parent=None) -> None:
        super().__init__(parent)
        self._retry = retry
        self.detail = _wrap("")
        self.countdown = QLabel()
        again = QPushButton(_("Try again now"))
        again.clicked.connect(self._fire)
        other = QPushButton(_("Settings…"))
        other.clicked.connect(settings)
        row = QWidget()
        buttons = QHBoxLayout(row)
        buttons.addWidget(other)
        buttons.addStretch(1)
        buttons.addWidget(again)
        QVBoxLayout(self).addWidget(_card(_title(_("Can't connect to Home Assistant")),
                                          self.detail, self.countdown, row))
        self._remaining = 0
        self._timer = QTimer(self, interval=1000)
        self._timer.timeout.connect(self._tick)

    def show_error(self, message: str) -> None:
        self.detail.setText(message)
        self._remaining = RETRY_SECONDS
        self._tick_label()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._remaining -= 1
        if self._remaining <= 0:
            self._fire()
        else:
            self._tick_label()

    def _tick_label(self) -> None:
        self.countdown.setText(_("Retrying automatically in {seconds} s…").format(seconds=self._remaining))

    def _fire(self) -> None:
        self._timer.stop()
        self._retry()


class MainWindow(QMainWindow):
    def __init__(self, app: "HaDesktop") -> None:
        super().__init__()
        self.app = app
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1280, 820)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.onboarding = Onboarding(app.config, app.api, app.tokens)
        self.onboarding.finished.connect(app.onboarding_finished)

        browser = QWidget()
        col = QVBoxLayout(browser)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.banner = self._make_banner()
        col.addWidget(self.banner)
        self.view = HaView(app.config, app.profile)
        self.view.settings_requested.connect(app.open_settings)
        self.view.load_failed.connect(self._load_failed)
        self.view.titleChanged.connect(self._title_changed)
        self.view.loadFinished.connect(self._load_finished)
        col.addWidget(self.view)

        self.error = ErrorPage(self.view.reload, app.open_settings)

        for page in (self.onboarding, browser, self.error):
            self.stack.addWidget(page)
        self.browser_page = browser

        shortcuts = [
            (QKeySequence.StandardKey.Refresh, self.view.reload),
            ("Ctrl+R", self.view.reload),
            ("Alt+Left", self.view.back),
            ("Alt+Right", self.view.forward),
            ("Alt+Home", lambda: self.view.open_path("")),
            ("F11", self.toggle_fullscreen),
            ("Ctrl+=", lambda: self.view.change_zoom(0.1)),
            ("Ctrl++", lambda: self.view.change_zoom(0.1)),
            ("Ctrl+-", lambda: self.view.change_zoom(-0.1)),
            ("Ctrl+0", lambda: self.view.change_zoom(None)),
            ("Ctrl+,", app.open_settings),
            ("Ctrl+Q", app.quit),
        ]
        for key, slot in shortcuts:
            QShortcut(QKeySequence(key), self, activated=slot)

    def _make_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("banner")
        banner.setStyleSheet("#banner { background: palette(alternate-base); border-bottom: 1px solid palette(mid); }")
        row = QHBoxLayout(banner)
        row.setContentsMargins(12, 6, 6, 6)
        row.addWidget(QLabel(_("Get Home Assistant notifications on this computer?")), 1)
        setup = QPushButton(_("Set up…"))
        setup.clicked.connect(self.app.open_settings)
        dismiss = QPushButton(_("Not now"))
        dismiss.setFlat(True)
        dismiss.clicked.connect(self._dismiss_banner)
        row.addWidget(setup)
        row.addWidget(dismiss)
        banner.hide()
        return banner

    def _dismiss_banner(self) -> None:
        self.app.config.notif_prompt_dismissed = True
        self.app.config.save()
        self.banner.hide()

    def update_banner(self) -> None:
        cfg = self.app.config
        self.banner.setVisible(not cfg.notifications and not cfg.notif_prompt_dismissed)

    def show_onboarding(self) -> None:
        self.error.stop()
        self.onboarding.restart()
        self.stack.setCurrentWidget(self.onboarding)

    def show_browser(self, target: str = "") -> None:
        self.error.stop()
        self.stack.setCurrentWidget(self.browser_page)
        self.update_banner()
        self.view.open_path(target)

    def _load_failed(self, message: str) -> None:
        if self.stack.currentWidget() is self.onboarding:
            return
        self.stack.setCurrentWidget(self.error)
        self.error.show_error(_("{url} can't be reached.").format(url=self.app.config.server_url)
                              + f"<br><small>{message}</small>")

    def _load_finished(self, ok: bool) -> None:
        if ok and self.stack.currentWidget() is self.error:
            self.error.stop()
            self.stack.setCurrentWidget(self.browser_page)

    def _title_changed(self, title: str) -> None:
        # HA zet bijv. "Overzicht – Home Assistant"; houd het kort.
        title = title.replace(" – Home Assistant", "").replace(" - Home Assistant", "").strip()
        self.setWindowTitle(f"{title} — {APP_NAME}" if title and "://" not in title else APP_NAME)

    def toggle_fullscreen(self) -> None:
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def closeEvent(self, event) -> None:
        if self.app.tray and self.app.config.close_to_tray and not self.app.quitting:
            event.ignore()
            self.hide()
        else:
            event.accept()
            self.app.quit()


class HaDesktop:
    def __init__(self, qapp: QApplication, start_hidden: bool) -> None:
        self.qapp = qapp
        self.quitting = False
        self.config = Config.load()
        self.tokens = TokenStore()
        self.api = HaApi(self.config)
        self.profile = make_profile(qapp)
        self.push = PushClient(self.config)
        self.notifier = Notifier()
        self.tray: QSystemTrayIcon | None = None

        self.window = MainWindow(self)
        self._setup_tray()
        self.notifier.set_tray(self.tray)
        self.notifier.clicked.connect(self.open_target)
        self.push.notification.connect(self._on_notification)
        self.push.status_changed.connect(self._on_push_status)
        self.profile.setNotificationPresenter(self._present_web_notification)
        if sys.platform == "darwin":
            # Klik op het Dock-icoon: verborgen venster weer tonen.
            qapp.applicationStateChanged.connect(self._on_app_state)

        if self.config.is_configured:
            self.window.show_browser()
            self.restart_push()
        else:
            self.window.show_onboarding()

        if not (start_hidden and self.tray and self.config.is_configured):
            self.show_window()

    # -- venster en systeemvak -----------------------------------------------

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(app_icon(), self.qapp)
        tray.setToolTip(APP_NAME)
        menu = QMenu()
        for text, slot in [(_("Open"), self.show_window), (_("Reload"), self.window.view.reload),
                           (_("Settings…"), self.open_settings)]:
            menu.addAction(QAction(text, menu, triggered=slot))
        menu.addSeparator()
        menu.addAction(QAction(_("Quit"), menu, triggered=self.quit))
        tray.setContextMenu(menu)
        self._tray_menu = menu
        tray.activated.connect(self._tray_activated)
        tray.show()
        self.tray = tray

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.window.isVisible() and self.window.isActiveWindow():
                self.window.hide()
            else:
                self.show_window()

    def show_window(self) -> None:
        self.window.show()
        self.window.setWindowState(self.window.windowState() & ~Qt.WindowState.WindowMinimized)
        self.window.raise_()
        self.window.activateWindow()

    def open_target(self, target: str) -> None:
        self.show_window()
        if self.config.is_configured:
            self.window.show_browser(target)

    def open_settings(self) -> None:
        if not self.config.is_configured:
            return
        self.show_window()
        dialog = SettingsDialog(self.config, self.api, self.tokens, self.push,
                                self.tray is not None, self.window)
        dialog.change_server.connect(self.change_server)
        dialog.open_path.connect(self.open_target)
        dialog.notifications_changed.connect(self.restart_push)
        dialog.notifications_changed.connect(self.window.update_banner)
        dialog.exec()
        dialog.deleteLater()

    def change_server(self) -> None:
        self.push.stop()
        self.window.show_onboarding()

    def onboarding_finished(self) -> None:
        self.window.show_browser()
        self.restart_push()

    def quit(self) -> None:
        self.quitting = True
        self.push.stop()
        self.notifier.close_all()
        # Pagina vóór het profiel opruimen, anders klaagt QtWebEngine.
        self.window.view.setPage(None)
        if self.tray:
            self.tray.hide()
        self.qapp.quit()

    # -- meldingen ------------------------------------------------------------

    def restart_push(self) -> None:
        cfg = self.config
        token = self.tokens.get(cfg.server_url) if cfg.notifications else ""
        if cfg.notifications and cfg.is_registered and token:
            self.push.start(cfg.server_url, token, cfg.webhook_id)
        else:
            self.push.stop()

    def _on_notification(self, event: dict) -> None:
        self.notifier.show(str(event.get("title") or ""), str(event.get("message") or ""),
                           notification_target(event))

    def _on_push_status(self, state: str, detail: str) -> None:
        if self.tray:
            text = {"connected": _("notifications active"), "error": _("notifications: error"),
                    "connecting": _("connecting…")}.get(state, _("not connected"))
            self.tray.setToolTip(f"{APP_NAME} — {text}")
        if state == "error":
            self.notifier.show(APP_NAME, detail)

    def _present_web_notification(self, notification) -> None:
        self.notifier.show(notification.title(), notification.message())

    def _on_app_state(self, state) -> None:
        if (state == Qt.ApplicationState.ApplicationActive and not self.quitting
                and not self.window.isVisible()):
            self.show_window()

    def wake(self) -> None:
        """Aangeroepen als een tweede instantie wordt gestart."""
        self.show_window()
        self.push.reconnect_now()


def _claim_single_instance(app: HaDesktop | None = None) -> QLocalServer | None:
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_KEY)
    if socket.waitForConnected(300):
        socket.write(b"show")
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return None
    QLocalServer.removeServer(INSTANCE_KEY)
    server = QLocalServer()
    server.listen(INSTANCE_KEY)
    return server


def _userns_restricted() -> bool:
    try:
        with open("/proc/sys/kernel/apparmor_restrict_unprivileged_userns") as f:
            return f.read().strip() == "1"
    except OSError:
        return False


def _self_test(qapp: QApplication) -> int:
    """Controleert of een gebundelde build compleet is (gebruikt in CI)."""
    from PySide6.QtWebEngineWidgets import QWebEngineView

    from ha_desktop.resources import icon_path

    print("icon:", icon_path().exists(), "| taal:", language(),
          "| keyring:", type(TokenStore()._keyring or TokenStore()._secret).__name__)
    view = QWebEngineView()
    result: list[bool] = []
    view.loadFinished.connect(lambda ok: (result.append(ok), qapp.quit()))
    QTimer.singleShot(90_000, qapp.quit)
    view.setHtml("<title>ok</title><p>ok</p>")
    qapp.exec()
    ok = bool(result and result[0] and icon_path().exists())
    print("self-test:", "OK" if ok else "MISLUKT")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ha-desktop", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--hidden", action="store_true", help=_("start hidden in the system tray"))
    parser.add_argument("--debug", action="store_true", help=_("verbose logging"))
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    args, qt_args = parser.parse_known_args(argv[1:])
    if getattr(sys, "frozen", False) and sys.platform.startswith("linux") and _userns_restricted():
        # Ubuntu 24.04+ staat de Chromium-sandbox alleen toe met een AppArmor-profiel;
        # zonder dat start de webweergave niet. De app laadt alleen je eigen server.
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    if sys.platform == "win32":
        # Eigen taakbalkgroep en icoon in plaats van die van Python.
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

    qapp = QApplication([argv[0], *qt_args])
    qapp.setApplicationName("ha-desktop")
    qapp.setApplicationDisplayName(APP_NAME)
    qapp.setApplicationVersion(__version__)
    qapp.setDesktopFileName(APP_ID)
    qapp.setWindowIcon(app_icon())
    qapp.setQuitOnLastWindowClosed(False)
    # Standaardknoppen (Ja/Nee, OK) in dezelfde taal als de app.
    translator = QTranslator(qapp)
    if translator.load(QLocale(language()), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        qapp.installTranslator(translator)

    if args.self_test:
        return _self_test(qapp)

    server = _claim_single_instance()
    if server is None:
        log.info("%s draait al; bestaand venster getoond", APP_NAME)
        return 0

    app = HaDesktop(qapp, args.hidden)

    def on_connection() -> None:
        conn = server.nextPendingConnection()
        conn.readyRead.connect(app.wake)
        conn.disconnected.connect(conn.deleteLater)

    server.newConnection.connect(on_connection)
    return qapp.exec()
