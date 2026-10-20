"""REST-aanroepen naar Home Assistant: server controleren en apparaat registreren."""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QByteArray, QObject, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from ha_desktop import APP_ID, APP_NAME, __version__
from ha_desktop.config import Config

TIMEOUT_MS = 8000


@dataclass
class Result:
    ok: bool
    error: str = ""
    # Gezet als de verbinding faalde op een niet-vertrouwd certificaat.
    cert_host: str = ""
    data: dict | None = None


class HaApi(QObject):
    def __init__(self, config: Config, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.nam = QNetworkAccessManager(self)
        self.nam.sslErrors.connect(self._on_ssl_errors)
        self._cert_failed: set[int] = set()

    def _on_ssl_errors(self, reply: QNetworkReply, errors) -> None:
        if self.config.trusts(reply.url().host()):
            reply.ignoreSslErrors()
        else:
            self._cert_failed.add(id(reply))

    def _send(self, method: str, url: str, callback: Callable[[QNetworkReply, bool], None],
              body: dict | None = None, token: str = "") -> None:
        req = QNetworkRequest(QUrl(url))
        req.setTransferTimeout(TIMEOUT_MS)
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        if token:
            req.setRawHeader(b"Authorization", f"Bearer {token}".encode())
        if body is not None:
            req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
            reply = self.nam.post(req, QByteArray(json.dumps(body).encode()))
        else:
            reply = self.nam.get(req)

        def done() -> None:
            cert_failed = id(reply) in self._cert_failed
            self._cert_failed.discard(id(reply))
            try:
                callback(reply, cert_failed)
            finally:
                reply.deleteLater()

        reply.finished.connect(done)

    @staticmethod
    def _network_error(reply: QNetworkReply) -> str:
        err = reply.error()
        E = QNetworkReply.NetworkError
        if err in (E.HostNotFoundError,):
            return "Server niet gevonden. Controleer het adres."
        if err in (E.ConnectionRefusedError,):
            return "Verbinding geweigerd. Klopt de poort (meestal 8123)?"
        if err in (E.TimeoutError, E.OperationCanceledError):
            return "De server reageert niet (time-out)."
        if err == E.SslHandshakeFailedError:
            return "Beveiligde verbinding mislukt."
        return f"Verbinding mislukt: {reply.errorString()}"

    def probe(self, base_url: str, callback: Callable[[Result], None]) -> None:
        """Controleer of er op base_url een Home Assistant-server draait."""

        def handle(reply: QNetworkReply, cert_failed: bool) -> None:
            if cert_failed:
                callback(Result(False, "Het certificaat van deze server wordt niet vertrouwd.",
                                cert_host=reply.url().host()))
                return
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if reply.error() != QNetworkReply.NetworkError.NoError and not status:
                callback(Result(False, self._network_error(reply)))
                return
            try:
                payload = json.loads(bytes(reply.readAll().data()))
            except ValueError:
                payload = None
            # Oudere versies geven een lijst terug, nieuwere {"providers": [...]}.
            providers = payload.get("providers") if isinstance(payload, dict) else payload
            if status == 200 and isinstance(providers, list):
                callback(Result(True))
            else:
                callback(Result(False, "Er reageert een server, maar het lijkt geen Home Assistant te zijn."))

        self._send("GET", f"{base_url}/auth/providers", handle)

    def register_device(self, base_url: str, token: str, callback: Callable[[Result], None]) -> None:
        """Registreer deze computer als mobile_app-apparaat met lokaal push-kanaal.

        Daarna verschijnt in Home Assistant de actie notify.mobile_app_<apparaatnaam>.
        """
        body = {
            "device_id": self.config.device_id,
            "app_id": APP_ID,
            "app_name": APP_NAME,
            "app_version": __version__,
            "device_name": self.config.device_name,
            "manufacturer": platform.system(),
            "model": f"{APP_NAME} ({platform.machine()})",
            "os_name": "Linux",
            "os_version": platform.release(),
            "supports_encryption": False,
            "app_data": {"push_websocket_channel": True},
        }

        def handle(reply: QNetworkReply, cert_failed: bool) -> None:
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if cert_failed:
                callback(Result(False, "Het certificaat van de server wordt niet vertrouwd.",
                                cert_host=reply.url().host()))
            elif status == 401:
                callback(Result(False, "Het token is ongeldig of verlopen."))
            elif status == 404:
                callback(Result(False, "De integratie 'Mobile App' is niet actief in Home Assistant."))
            elif status not in (200, 201):
                callback(Result(False, self._network_error(reply) if not status
                                else f"Registratie mislukt (HTTP {status})."))
            else:
                try:
                    data = json.loads(bytes(reply.readAll().data()))
                except ValueError:
                    data = {}
                if data.get("webhook_id"):
                    callback(Result(True, data=data))
                else:
                    callback(Result(False, "Onverwacht antwoord van Home Assistant."))

        self._send("POST", f"{base_url}/api/mobile_app/registrations", handle, body=body, token=token)
