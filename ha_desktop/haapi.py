"""Losse aanroepen naar Home Assistant: server controleren, apparaat registreren, entiteiten ophalen.

Meestal via REST; de registers (ruimtes, apparaten) zijn alleen via de websocket op te vragen.
"""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from ha_desktop import APP_ID, APP_NAME, __version__
from ha_desktop.config import Config
from ha_desktop.hasocket import HaSocket
from ha_desktop.i18n import _

TIMEOUT_MS = 8000


@dataclass
class Result:
    ok: bool
    error: str = ""
    # Gezet als de verbinding faalde op een niet-vertrouwd certificaat.
    cert_host: str = ""
    data: dict | None = None


class _WsRequest(HaSocket):
    """Eén keer verbinden, opdrachten sturen en de antwoorden teruggeven (zonder opnieuw proberen)."""

    def __init__(self, config: Config, messages: list[dict], callback: Callable[[Result], None]) -> None:
        super().__init__(config)
        self._messages, self._callback = messages, callback
        self._ids: list[int] = []
        self._results: dict[int, object] = {}
        self._timeout = QTimer(self, singleShot=True, interval=TIMEOUT_MS)
        self._timeout.timeout.connect(lambda: self._finish(Result(False, _("The server is not responding (timeout)."))))
        self.status_changed.connect(lambda state, detail: state == "error" and self._finish(Result(False, detail)))

    def start(self, base_url: str, token: str) -> None:
        self._timeout.start()
        super().start(base_url, token)

    def _subscribe(self) -> None:
        self._ids = [self._send(dict(m)) for m in self._messages]

    def _handle(self, msg: dict) -> None:
        if msg.get("type") != "result" or msg.get("id") not in self._ids:
            return
        if not msg.get("success"):
            err = (msg.get("error") or {}).get("message", "")
            self._finish(Result(False, _("Home Assistant refused the request: {error}").format(error=err)))
            return
        self._results[msg["id"]] = msg.get("result")
        if len(self._results) == len(self._ids):
            self._finish(Result(True, data={"results": [self._results[i] for i in self._ids]}))

    def _on_disconnected(self) -> None:
        reason = self._ws.errorString() if self._ws else ""
        self._finish(Result(False, _("Connection failed: {error}").format(error=reason)))

    def _finish(self, result: Result) -> None:
        callback, self._callback = self._callback, None
        if callback is None:
            return
        self._timeout.stop()
        self.stop()
        self.deleteLater()
        callback(result)


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
            return _("Server not found. Check the address.")
        if err in (E.ConnectionRefusedError,):
            return _("Connection refused. Is the port correct (usually 8123)?")
        if err in (E.TimeoutError, E.OperationCanceledError):
            return _("The server is not responding (timeout).")
        if err == E.SslHandshakeFailedError:
            return _("Secure connection failed.")
        return _("Connection failed: {error}").format(error=reply.errorString())

    def _failure(self, reply: QNetworkReply, cert_failed: bool, auth: bool = True) -> Result | None:
        """De fouten die elke aanvraag kan krijgen: certificaat, token, geen verbinding."""
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if cert_failed:
            return Result(False, _("This server's certificate is not trusted."), cert_host=reply.url().host())
        if auth and status == 401:
            return Result(False, _("The token is invalid or has expired."))
        if not status:
            return Result(False, self._network_error(reply))
        return None

    def probe(self, base_url: str, callback: Callable[[Result], None]) -> None:
        """Controleer of er op base_url een Home Assistant-server draait."""

        def handle(reply: QNetworkReply, cert_failed: bool) -> None:
            failure = self._failure(reply, cert_failed, auth=False)
            if failure:
                callback(failure)
                return
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            try:
                payload = json.loads(bytes(reply.readAll().data()))
            except ValueError:
                payload = None
            # Oudere versies geven een lijst terug, nieuwere {"providers": [...]}.
            providers = payload.get("providers") if isinstance(payload, dict) else payload
            if status == 200 and isinstance(providers, list):
                callback(Result(True))
            else:
                callback(Result(False, _("A server responded, but it doesn't look like Home Assistant.")))

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
            failure = self._failure(reply, cert_failed)
            if failure:
                callback(failure)
            elif status == 404:
                callback(Result(False, _("The 'Mobile App' integration is not enabled in Home Assistant.")))
            elif status not in (200, 201):
                callback(Result(False, _("Registration failed (HTTP {status}).").format(status=status)))
            else:
                try:
                    data = json.loads(bytes(reply.readAll().data()))
                except ValueError:
                    data = {}
                if data.get("webhook_id"):
                    callback(Result(True, data=data))
                else:
                    callback(Result(False, _("Unexpected response from Home Assistant.")))

        self._send("POST", f"{base_url}/api/mobile_app/registrations", handle, body=body, token=token)

    def get_states(self, base_url: str, token: str, callback: Callable[[Result], None]) -> None:
        """Haal alle entiteiten op; Result.data["states"] is de lijst van /api/states."""

        def handle(reply: QNetworkReply, cert_failed: bool) -> None:
            failure = self._failure(reply, cert_failed)
            if failure:
                callback(failure)
                return
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            try:
                payload = json.loads(bytes(reply.readAll().data()))
            except ValueError:
                payload = None
            if status == 200 and isinstance(payload, list):
                callback(Result(True, data={"states": payload}))
            else:
                callback(Result(False, _("Unexpected response from Home Assistant.")))

        self._send("GET", f"{base_url}/api/states", handle, token=token)

    def ws_request(self, base_url: str, token: str, messages: list[dict],
                   callback: Callable[[Result], None]) -> None:
        """Stuur websocket-opdrachten; Result.data["results"] bevat de antwoorden in volgorde."""
        request = _WsRequest(self.config, messages, callback)
        request.setParent(self)
        request.start(base_url, token)
