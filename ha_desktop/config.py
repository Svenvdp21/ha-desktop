"""Instellingen (JSON in ~/.config) en opslag van het toegangstoken (keyring)."""

from __future__ import annotations

import json
import logging
import os
import socket
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from urllib.parse import urlsplit

from ha_desktop import APP_ID, APP_NAME
from ha_desktop.i18n import _

log = logging.getLogger(__name__)


def _xdg(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / fallback)


def config_dir() -> Path:
    override = os.environ.get("HA_DESKTOP_CONFIG_DIR")
    return Path(override) if override else _xdg("XDG_CONFIG_HOME", ".config") / "ha-desktop"


def data_dir() -> Path:
    override = os.environ.get("HA_DESKTOP_DATA_DIR")
    return Path(override) if override else _xdg("XDG_DATA_HOME", ".local/share") / "ha-desktop"


def cache_dir() -> Path:
    return _xdg("XDG_CACHE_HOME", ".cache") / "ha-desktop"


@dataclass
class Config:
    server_url: str = ""
    notifications: bool = False
    # Webhook van de mobile_app-registratie, en voor welke server die geldt.
    webhook_id: str = ""
    registered_for: str = ""
    device_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    device_name: str = field(default_factory=socket.gethostname)
    close_to_tray: bool = True
    notif_prompt_dismissed: bool = False
    trusted_hosts: list[str] = field(default_factory=list)
    zoom: float = 1.0

    @classmethod
    def load(cls) -> "Config":
        path = config_dir() / "config.json"
        try:
            raw = json.loads(path.read_text())
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError) as exc:
            # Kapot bestand niet stilletjes weggooien: bewaar een kopie.
            log.warning("Kan %s niet lezen (%s); standaardwaarden gebruikt", path, exc)
            try:
                path.replace(path.with_suffix(".json.bak"))
            except OSError:
                pass
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        directory = config_dir()
        directory.mkdir(parents=True, exist_ok=True)
        tmp = directory / "config.json.tmp"
        tmp.write_text(json.dumps(asdict(self), indent=2))
        os.chmod(tmp, 0o600)
        os.replace(tmp, directory / "config.json")

    @property
    def is_configured(self) -> bool:
        return bool(self.server_url)

    @property
    def is_registered(self) -> bool:
        return bool(self.webhook_id) and self.registered_for == self.server_url

    def trust_host(self, host: str) -> None:
        if host and host not in self.trusted_hosts:
            self.trusted_hosts.append(host)

    def trusts(self, host: str) -> bool:
        return host in self.trusted_hosts


def normalize_url(text: str) -> list[str]:
    """Zet gebruikersinvoer om in te proberen basis-URL's (zonder pad).

    Zonder schema proberen we eerst https en daarna http.
    """
    text = text.strip()
    if not text:
        raise ValueError(_("Enter the address of your Home Assistant server."))
    has_scheme = "://" in text
    parts = urlsplit(text if has_scheme else f"http://{text}")
    if parts.scheme not in ("http", "https"):
        raise ValueError(_("The address must start with http:// or https://."))
    if not parts.hostname:
        raise ValueError(_("This doesn't look like a valid address."))
    try:
        parts.port
    except ValueError:
        raise ValueError(_("The port number is invalid.")) from None
    netloc = parts.netloc.rsplit("@", 1)[-1]
    if has_scheme:
        return [f"{parts.scheme}://{netloc}"]
    return [f"https://{netloc}", f"http://{netloc}"]


class TokenStore:
    """Bewaart het long-lived access token in de systeem-keyring (Secret Service).

    Valt terug op een bestand met rechten 0600 als er geen keyring beschikbaar is.
    """

    def __init__(self) -> None:
        self._secret = None
        try:
            import gi

            gi.require_version("Secret", "1")
            from gi.repository import Secret

            self._secret = Secret
            self._schema = Secret.Schema.new(
                APP_ID, Secret.SchemaFlags.NONE, {"server": Secret.SchemaAttributeType.STRING}
            )
        except (ImportError, ValueError) as exc:
            log.info("libsecret niet beschikbaar (%s); token wordt in een bestand bewaard", exc)

    def _file(self) -> Path:
        return config_dir() / "token"

    def get(self, server: str) -> str:
        if self._secret:
            try:
                value = self._secret.password_lookup_sync(self._schema, {"server": server}, None)
                if value:
                    return value
            except Exception as exc:  # noqa: BLE001 - keyring-daemon kan ontbreken
                log.warning("Keyring lezen mislukt: %s", exc)
        try:
            stored = json.loads(self._file().read_text())
            return stored.get(server, "")
        except (OSError, ValueError):
            return ""

    def set(self, server: str, token: str) -> None:
        if self._secret:
            try:
                self._secret.password_store_sync(
                    self._schema, {"server": server}, self._secret.COLLECTION_DEFAULT,
                    f"{APP_NAME} token ({server})", token, None,
                )
                self._remove_from_file(server)
                return
            except Exception as exc:  # noqa: BLE001
                log.warning("Keyring schrijven mislukt (%s); bestand gebruikt", exc)
        path = self._file()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            stored = json.loads(path.read_text())
        except (OSError, ValueError):
            stored = {}
        stored[server] = token
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(stored))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    def delete(self, server: str) -> None:
        if self._secret:
            try:
                self._secret.password_clear_sync(self._schema, {"server": server}, None)
            except Exception as exc:  # noqa: BLE001
                log.warning("Keyring wissen mislukt: %s", exc)
        self._remove_from_file(server)

    def _remove_from_file(self, server: str) -> None:
        path = self._file()
        try:
            stored = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        if stored.pop(server, None) is not None:
            path.write_text(json.dumps(stored))
