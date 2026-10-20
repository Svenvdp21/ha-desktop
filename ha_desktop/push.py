"""Ontvangt meldingen via het lokale push-kanaal van de mobile_app-integratie.

Protocol (zelfde aanpak als joshuar/go-hass-agent):
  auth_required -> auth -> auth_ok -> mobile_app/push_notification_channel
  Daarna komt elke melding binnen als "event" op het abonnements-id.
"""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QAbstractSocket
from PySide6.QtWebSockets import QWebSocket

from ha_desktop.config import Config

log = logging.getLogger(__name__)

PING_INTERVAL_MS = 30_000
PONG_TIMEOUT_MS = 15_000
MAX_BACKOFF_S = 60


def websocket_url(base_url: str) -> str:
    if base_url.startswith("https://"):
        return "wss://" + base_url[len("https://"):] + "/api/websocket"
    return "ws://" + base_url[len("http://"):] + "/api/websocket"


class PushClient(QObject):
    notification = Signal(dict)
    # state: "disconnected" | "connecting" | "connected" | "error"
    status_changed = Signal(str, str)

    def __init__(self, config: Config, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.state = "disconnected"
        self.detail = ""
        self._ws: QWebSocket | None = None
        self._base_url = self._token = self._webhook_id = ""
        self._next_id = 1
        self._sub_id = 0
        self._ping_id = 0
        self._attempt = 0
        self._running = False

        self._reconnect = QTimer(self, singleShot=True)
        self._reconnect.timeout.connect(self._connect)
        self._ping = QTimer(self, interval=PING_INTERVAL_MS)
        self._ping.timeout.connect(self._send_ping)
        self._pong_deadline = QTimer(self, singleShot=True, interval=PONG_TIMEOUT_MS)
        self._pong_deadline.timeout.connect(self._on_pong_timeout)

    # -- publieke API ---------------------------------------------------------

    def start(self, base_url: str, token: str, webhook_id: str) -> None:
        self.stop()
        self._base_url, self._token, self._webhook_id = base_url, token, webhook_id
        self._running = True
        self._attempt = 0
        self._connect()

    def stop(self) -> None:
        self._running = False
        self._reconnect.stop()
        self._ping.stop()
        self._pong_deadline.stop()
        if self._ws:
            ws, self._ws = self._ws, None
            ws.disconnected.disconnect()
            ws.close()
            ws.deleteLater()
        self._set_state("disconnected", "")

    def reconnect_now(self) -> None:
        """Bijv. na hervatten uit slaapstand: niet op de backoff wachten."""
        if self._running and self.state != "connected":
            self._attempt = 0
            self._connect()

    # -- intern ---------------------------------------------------------------

    def _set_state(self, state: str, detail: str) -> None:
        if (state, detail) != (self.state, self.detail):
            self.state, self.detail = state, detail
            self.status_changed.emit(state, detail)

    def _connect(self) -> None:
        if not self._running:
            return
        self._reconnect.stop()
        if self._ws:
            old, self._ws = self._ws, None
            old.disconnected.disconnect()
            old.abort()
            old.deleteLater()
        self._set_state("connecting", "")
        ws = QWebSocket()
        ws.setParent(self)
        ws.textMessageReceived.connect(self._on_message)
        ws.disconnected.connect(self._on_disconnected)
        ws.sslErrors.connect(lambda errors, ws=ws: self._on_ssl_errors(ws))
        self._ws = ws
        ws.open(QUrl(websocket_url(self._base_url)))

    def _on_ssl_errors(self, ws: QWebSocket) -> None:
        if self.config.trusts(ws.requestUrl().host()):
            ws.ignoreSslErrors()

    def _send(self, msg: dict) -> int:
        if "type" in msg and msg["type"] != "auth":
            msg["id"] = self._next_id
            self._next_id += 1
        if self._ws:
            self._ws.sendTextMessage(json.dumps(msg))
        return msg.get("id", 0)

    def _on_message(self, text: str) -> None:
        try:
            msg = json.loads(text)
        except ValueError:
            return
        # HA kan berichten bundelen in een lijst.
        for m in msg if isinstance(msg, list) else [msg]:
            self._handle(m)

    def _handle(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "auth_required":
            self._send({"type": "auth", "access_token": self._token})
        elif kind == "auth_ok":
            self._next_id = 1
            self._sub_id = self._send({
                "type": "mobile_app/push_notification_channel",
                "webhook_id": self._webhook_id,
                "support_confirm": True,
            })
        elif kind == "auth_invalid":
            self._running = False
            self._set_state("error", "Token geweigerd door Home Assistant. Maak een nieuw token aan.")
            if self._ws:
                self._ws.close()
        elif kind == "result" and msg.get("id") == self._sub_id:
            if msg.get("success"):
                self._attempt = 0
                self._ping.start()
                self._set_state("connected", "")
            else:
                self._running = False
                err = (msg.get("error") or {}).get("message", "onbekende fout")
                self._set_state("error", f"Abonneren op meldingen mislukt: {err}. "
                                         "Schakel meldingen opnieuw in om dit apparaat te registreren.")
                if self._ws:
                    self._ws.close()
        elif kind == "pong" and msg.get("id") == self._ping_id:
            self._pong_deadline.stop()
        elif kind == "event" and msg.get("id") == self._sub_id:
            event = msg.get("event") or {}
            confirm_id = event.get("confirm_id")
            if confirm_id:
                self._send({"type": "mobile_app/push_notification_confirm",
                            "webhook_id": self._webhook_id, "confirm_id": confirm_id})
            if event.get("message") == "clear_notification":
                return
            self.notification.emit(event)

    def _send_ping(self) -> None:
        if self._ws and self._ws.state() == QAbstractSocket.SocketState.ConnectedState:
            self._ping_id = self._send({"type": "ping"})
            self._pong_deadline.start()

    def _on_pong_timeout(self) -> None:
        log.info("Geen pong ontvangen; verbinding opnieuw opbouwen")
        if self._ws:
            self._ws.abort()

    def _on_disconnected(self) -> None:
        self._ping.stop()
        self._pong_deadline.stop()
        if not self._running:
            return
        delay = min(MAX_BACKOFF_S, 2 ** self._attempt)
        self._attempt += 1
        reason = self._ws.errorString() if self._ws else ""
        self._set_state("disconnected", f"Verbinding verbroken; opnieuw proberen over {delay} s. {reason}".strip())
        self._reconnect.start(delay * 1000)
