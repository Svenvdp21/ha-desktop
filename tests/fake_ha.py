"""Minimale nep-Home Assistant (HTTP + websocket op één poort) voor tests."""

from __future__ import annotations

import copy
import json

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QHostAddress, QTcpServer, QTcpSocket
from PySide6.QtWebSockets import QWebSocket, QWebSocketServer

TOKEN = "goed-token"
WEBHOOK = "webhook-123"
STATES = {
    "light.woonkamer": {"state": "on", "attributes": {
        "friendly_name": "Woonkamer", "supported_color_modes": ["brightness"], "brightness": 128}},
    "light.gang": {"state": "off", "attributes": {"friendly_name": "Gang", "supported_color_modes": ["onoff"]}},
    "switch.tv": {"state": "off", "attributes": {"friendly_name": "Stopcontact tv"}},
    "scene.film": {"state": "unknown", "attributes": {"friendly_name": "Film kijken"}},
    "sensor.temperatuur": {"state": "21.5", "attributes": {"friendly_name": "Temperatuur"}},
    "switch.led": {"state": "on", "attributes": {"friendly_name": "Ledje schakelaar"}},
    "light.verborgen": {"state": "off", "attributes": {"friendly_name": "Verborgen", "supported_color_modes": ["onoff"]}},
}
# Antwoorden op de registeropdrachten (alleen de velden die de app gebruikt).
REGISTRY = {
    "config/area_registry/list": [
        {"area_id": "woonkamer", "name": "Woonkamer", "icon": "mdi:sofa"},
        {"area_id": "keuken", "name": "Keuken", "icon": "mdi:fridge"},
        {"area_id": "zolder", "name": "Zolder", "icon": None},
    ],
    "config/device_registry/list": [{"id": "dev1", "area_id": "woonkamer"}],
    "config/entity_registry/list_for_display": {"entity_categories": {"0": "config", "1": "diagnostic"}, "entities": [
        {"ei": "light.woonkamer", "di": "dev1"},
        {"ei": "switch.tv", "ai": "woonkamer"},
        {"ei": "light.gang", "ai": "keuken"},
        {"ei": "switch.led", "ai": "woonkamer", "ec": 0},
        {"ei": "light.verborgen", "ai": "keuken", "hb": True},
    ]},
}


class FakeHA(QObject):
    confirmed = Signal(str)
    subscribed = Signal()
    called = Signal(dict)

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
        # False = HA is nog aan het opstarten: mobile_app-commando's bestaan nog niet.
        self.mobile_app_loaded = True
        self.states = copy.deepcopy(STATES)
        # Abonnementen van subscribe_entities: (websocket, id, entity_ids).
        self.entity_subs: list[tuple[QWebSocket, int, list[str]]] = []

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
        authorized = auth.strip() == f"Authorization: Bearer {TOKEN}"
        if method == "GET" and path == "/auth/providers":
            return 200, {"providers": [{"name": "Home Assistant Local", "type": "homeassistant"}]}
        if method == "GET" and path == "/api/states":
            if not authorized:
                return 401, {"message": "Unauthorized"}
            return 200, [{"entity_id": e, **s} for e, s in self.states.items()]
        if method == "POST" and path == "/api/mobile_app/registrations":
            if not authorized:
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
        elif msg["type"].startswith("mobile_app/") and not self.mobile_app_loaded:
            ws.sendTextMessage(json.dumps({"id": msg["id"], "type": "result", "success": False,
                                           "error": {"code": "unknown_command", "message": "Unknown command."}}))
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
        elif msg["type"] == "subscribe_entities":
            ids = msg.get("entity_ids") or list(self.states)
            self.entity_subs.append((ws, msg["id"], ids))
            ws.sendTextMessage(json.dumps({"id": msg["id"], "type": "result", "success": True, "result": None}))
            initial = {e: {"s": self.states[e]["state"], "a": self.states[e]["attributes"], "lc": 0}
                       for e in ids if e in self.states}
            ws.sendTextMessage(json.dumps({"id": msg["id"], "type": "event", "event": {"a": initial}}))
        elif msg["type"] == "call_service":
            self._call_service(ws, msg)
        elif msg["type"] in REGISTRY:
            ws.sendTextMessage(json.dumps({"id": msg["id"], "type": "result", "success": True,
                                           "result": REGISTRY[msg["type"]]}))
        else:
            ws.sendTextMessage(json.dumps({"id": msg["id"], "type": "result", "success": False,
                                           "error": {"code": "unknown_command", "message": "Unknown command."}}))

    def _call_service(self, ws: QWebSocket, msg: dict) -> None:
        """Genoeg van light/switch/scene om de snelbediening te testen."""
        entity_id = msg["target"]["entity_id"]
        data = msg.get("service_data") or {}
        self.called.emit({"domain": msg["domain"], "service": msg["service"], "entity_id": entity_id, **data})
        state = self.states.get(entity_id)
        if state is None:
            ws.sendTextMessage(json.dumps({"id": msg["id"], "type": "result", "success": False, "error": {
                "code": "service_validation_error", "message": f"Entity {entity_id} not found"}}))
            return
        service = msg["service"]
        if msg["domain"] == "scene":
            new, attrs, removed = "2026-11-01T12:00:00+00:00", {}, []
        elif service == "turn_off" or (service == "toggle" and state["state"] == "on"):
            new, attrs, removed = "off", {}, ["brightness"] if "brightness" in state["attributes"] else []
        else:
            new, removed = "on", []
            attrs = {"brightness": round(data.get("brightness_pct", 100) * 255 / 100)} \
                if entity_id.startswith("light.") and "brightness_pct" in data else {}
        state["state"] = new
        state["attributes"].update(attrs)
        for key in removed:
            state["attributes"].pop(key)
        diff = {"+": {"s": new, "a": attrs}}
        if removed:
            diff["-"] = {"a": removed}
        self._entity_event(entity_id, {"c": {entity_id: diff}})
        ws.sendTextMessage(json.dumps({"id": msg["id"], "type": "result", "success": True, "result": None}))

    def _entity_event(self, entity_id: str, event: dict) -> None:
        for ws, sub_id, ids in self.entity_subs:
            if entity_id in ids and ws in self.clients:
                ws.sendTextMessage(json.dumps({"id": sub_id, "type": "event", "event": event}))

    def remove_entity(self, entity_id: str) -> None:
        del self.states[entity_id]
        self._entity_event(entity_id, {"r": [entity_id]})

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
