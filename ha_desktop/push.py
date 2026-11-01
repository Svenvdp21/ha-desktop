"""Ontvangt meldingen via het lokale push-kanaal van de mobile_app-integratie.

Protocol (zelfde aanpak als joshuar/go-hass-agent):
  auth_required -> auth -> auth_ok -> mobile_app/push_notification_channel
  Daarna komt elke melding binnen als "event" op het abonnements-id.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from ha_desktop.config import Config
from ha_desktop.hasocket import HaSocket
from ha_desktop.i18n import _

log = logging.getLogger(__name__)


class PushClient(HaSocket):
    notification = Signal(dict)

    def __init__(self, config: Config, parent: QObject | None = None) -> None:
        super().__init__(config, parent)
        self._webhook_id = ""
        self._sub_id = 0

    def start(self, base_url: str, token: str, webhook_id: str) -> None:
        self._webhook_id = webhook_id
        super().start(base_url, token)

    def _subscribe(self) -> None:
        self._sub_id = self._send({
            "type": "mobile_app/push_notification_channel",
            "webhook_id": self._webhook_id,
            "support_confirm": True,
        })

    def _handle(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "result" and msg.get("id") == self._sub_id:
            if msg.get("success"):
                self._subscribed()
            else:
                error = msg.get("error") or {}
                if error.get("code") == "unknown_command":
                    # Vlak na een herstart accepteert HA de websocket al voordat mobile_app geladen is.
                    # Tijdelijk: sluiten en via de gewone backoff opnieuw proberen.
                    log.info("mobile_app nog niet geladen; opnieuw proberen")
                    if self._ws:
                        self._ws.close()
                    return
                err = error.get("message") or _("unknown error")
                self._fail(_("Subscribing to notifications failed: {error}. Turn notifications "
                             "on again to register this device.").format(error=err))
        elif kind == "event" and msg.get("id") == self._sub_id:
            event = msg.get("event") or {}
            confirm_id = event.get("confirm_id")
            if confirm_id:
                self._send({"type": "mobile_app/push_notification_confirm",
                            "webhook_id": self._webhook_id, "confirm_id": confirm_id})
            if event.get("message") == "clear_notification":
                return
            self.notification.emit(event)
