"""Ingebedde browser voor de Home Assistant-webinterface."""

from __future__ import annotations

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWebEngineCore import (
    QWebEngineCertificateError,
    QWebEngineLoadingInfo,
    QWebEnginePage,
    QWebEnginePermission,
    QWebEngineProfile,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMessageBox, QWidget

from ha_desktop.config import Config, cache_dir, data_dir

# Rechten die we aan de eigen server geven: meldingen en microfoon (Assist).
_GRANTED = {
    QWebEnginePermission.PermissionType.Notifications,
    QWebEnginePermission.PermissionType.MediaAudioCapture,
}


def make_profile(parent) -> QWebEngineProfile:
    """Persistent profiel, zodat je ingelogd blijft na herstarten."""
    profile = QWebEngineProfile("ha-desktop", parent)
    profile.setPersistentStoragePath(str(data_dir() / "webengine"))
    profile.setCachePath(str(cache_dir() / "webengine"))
    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
    return profile


def same_origin(a: QUrl, b: QUrl) -> bool:
    return (a.scheme(), a.host(), a.port(-1)) == (b.scheme(), b.host(), b.port(-1))


class _ExternalOpener(QWebEnginePage):
    """Vangt target=_blank-links af en opent ze in de standaardbrowser."""

    def acceptNavigationRequest(self, url, nav_type, is_main_frame) -> bool:
        QDesktopServices.openUrl(url)
        self.deleteLater()
        return False


class HaPage(QWebEnginePage):
    def __init__(self, profile: QWebEngineProfile, config: Config, parent=None) -> None:
        super().__init__(profile, parent)
        self.config = config
        self.certificateError.connect(self._on_certificate_error)
        self.permissionRequested.connect(self._on_permission)

    def server(self) -> QUrl:
        return QUrl(self.config.server_url)

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:
        external = url.scheme() in ("http", "https") and not same_origin(url, self.server())
        if external and is_main_frame and nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            QDesktopServices.openUrl(url)
            return False
        if url.scheme() in ("mailto", "tel"):
            QDesktopServices.openUrl(url)
            return False
        return True

    def createWindow(self, _type) -> QWebEnginePage:
        return _ExternalOpener(self.profile(), self)

    def _on_permission(self, permission: QWebEnginePermission) -> None:
        if (permission.permissionType() in _GRANTED
                and same_origin(permission.origin(), self.server())):
            permission.grant()
        else:
            permission.deny()

    def _on_certificate_error(self, error: QWebEngineCertificateError) -> None:
        if self.config.trusts(error.url().host()):
            error.acceptCertificate()
        else:
            error.rejectCertificate()


class HaView(QWebEngineView):
    settings_requested = Signal()
    load_failed = Signal(str)

    def __init__(self, config: Config, profile: QWebEngineProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.setPage(HaPage(profile, config, self))
        self.page().loadingChanged.connect(self._on_loading_changed)
        self.page().renderProcessTerminated.connect(self._on_crash)
        self.setZoomFactor(config.zoom)

    def open_path(self, target: str = "") -> None:
        """Open een pad (/lovelace/0) of volledige URL op de eigen server."""
        base = QUrl(self.config.server_url)
        url = base.resolved(QUrl(target)) if target else base
        if target and not same_origin(url, base):
            QDesktopServices.openUrl(url)
            return
        self.load(url)

    def change_zoom(self, delta: float | None) -> None:
        zoom = 1.0 if delta is None else max(0.5, min(2.0, round(self.zoomFactor() + delta, 2)))
        self.setZoomFactor(zoom)
        self.config.zoom = zoom
        self.config.save()

    def contextMenuEvent(self, event) -> None:
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        settings = QAction("Instellingen…", menu)
        settings.triggered.connect(self.settings_requested)
        menu.addAction(settings)
        menu.exec(event.globalPos())

    def _on_loading_changed(self, info: QWebEngineLoadingInfo) -> None:
        if info.status() != QWebEngineLoadingInfo.LoadStatus.LoadFailedStatus:
            return
        D = QWebEngineLoadingInfo.ErrorDomain
        if info.errorDomain() in (D.ConnectionErrorDomain, D.CertificateErrorDomain, D.DnsErrorDomain):
            self.load_failed.emit(info.errorString())
        elif info.errorDomain() == D.HttpErrorDomain and info.errorCode() >= 500:
            # Bijv. 502 van een reverse proxy terwijl HA herstart.
            self.load_failed.emit(f"De server gaf foutcode {info.errorCode()}.")

    def _on_crash(self, status, code) -> None:
        if status != QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus:
            QMessageBox.warning(self, "Pagina gecrasht", "De weergave is vastgelopen en wordt opnieuw geladen.")
            self.reload()
