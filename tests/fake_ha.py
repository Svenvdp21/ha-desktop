"""Minimale nep-Home Assistant (HTTP + websocket op één poort) voor tests."""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QHostAddress, QTcpServer, QTcpSocket
from PySide6.QtWebSockets import QWebSocket, QWebSocketServer

TOKEN = "goed-token"
WEBHOOK = "webhook-123"


class FakeHA(QObject):
    confirmed = Signal(str)
    subscribed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.tcp = QTcpServer(self)
        self.tcp.newConnection.connect(self._accept)
        self.tcp.listen(QHostAddress.SpecialAddress.LocalHost, 0)
        self.ws_server = QWebSocketServer("fake", QWebSocketServer.SslMode.NonSecureMode, self)
        self.ws_server.newConnection.connect(self._ws_accept)
        self.clients: list[QWebSocket] = []
        self.sub_id = 0
        self.registrations: list[dict] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.tcp.serverPort()}"

    def _accept(self) -> None:
        sock: QTcpSocket = self.tcp.nextPendingConnection()
        sock.readyRead.connect(lambda s=sock: self._read(s))

    def _read(self, sock: QTcpSocket) -> None:
        head = bytes(sock.peek(65536).data())
        if b"\r\n\r\n" not in head:
            return
        if b"upgrade: websocket" in head.lower():
            sock.readyRead.disconnect()
            self.ws_server.handleConnection(sock)
            return
        header, _, body = head.partition(b"\r\n\r\n")
        length = 0
        for line in header.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                length = int(line.split(b":")[1])
        if len(body) < length:
            return
        sock.read(len(header) + 4 + length)
        request_line = header.split(b"\r\n")[0].decode()
        method, path, _ = request_line.split(" ")
        auth = next((l for l in header.split(b"\r\n") if l.lower().startswith(b"authorization:")), b"")
        status, payload = self._route(method, path, auth.decode(), body[:length])
        data = json.dumps(payload).encode()
        sock.write(f"HTTP/1.1 {status} X\r\nContent-Type: application/json\r\n"
                   f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n".encode() + data)
        sock.disconnectFromHost()

    def _route(self, method: str, path: str, auth: str, body: bytes):
        if method == "GET" and path == "/auth/providers":
            return 200, {"providers": [{"name": "Home Assistant Local", "type": "homeassistant"}]}
        if method == "POST" and path == "/api/mobile_app/registrations":
            if auth.strip() != f"Authorization: Bearer {TOKEN}":
                return 401, {"message": "Unauthorized"}
            self.registrations.append(json.loads(body))
            return 201, {"webhook_id": WEBHOOK, "cloudhook_url": None, "remote_ui_url": None, "secret": None}
        return 404, {"message": "Not found"}

    def _ws_accept(self) -> None:
        ws = self.ws_server.nextPendingConnection()
        self.clients.append(ws)
        ws.textMessageReceived.connect(lambda t, ws=ws: self._ws_msg(ws, t))
        ws.sendTextMessage(json.dumps({"type": "auth_required", "ha_version": "2026.10.0"}))

    def _ws_msg(self, ws: QWebSocket, text: str) -> None:
        msg = json.loads(text)
        if msg["type"] == "auth":
            ok = msg["access_token"] == TOKEN
            ws.sendTextMessage(json.dumps({"type": "auth_ok" if ok else "auth_invalid"}))
        elif msg["type"] == "mobile_app/push_notification_channel":
            ok = msg["webhook_id"] == WEBHOOK and msg.get("support_confirm") is True
            self.sub_id = msg["id"]
            reply = {"id": msg["id"], "type": "result", "success": ok, "result": None}
            if not ok:
                reply["error"] = {"code": "not_found", "message": "Webhook ID not found"}
            ws.sendTextMessage(json.dumps(reply))
            if ok:
                self.subscribed.emit()
        elif msg["type"] == "mobile_app/push_notification_confirm":
            self.confirmed.emit(msg["confirm_id"])
            ws.sendTextMessage(json.dumps({"id": msg["id"], "type": "result", "success": True}))
        elif msg["type"] == "ping":
            ws.sendTextMessage(json.dumps({"id": msg["id"], "type": "pong"}))

    def push(self, title: str, message: str, data: dict | None = None, confirm_id: str = "") -> None:
        event = {"title": title, "message": message, "data": data or {}}
        if confirm_id:
            event["confirm_id"] = confirm_id
        for ws in self.clients:
            ws.sendTextMessage(json.dumps({"id": self.sub_id, "type": "event", "event": event}))

    def drop_clients(self) -> None:
        for ws in self.clients:
            ws.abort()
        self.clients.clear()
