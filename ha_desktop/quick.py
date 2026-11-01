"""Snelbediening: lampen, schakelaars en scènes bedienen vanuit het systeemvak.

De indeling (config.quick_layout) bestaat uit secties met tegels, zoals een
HA-dashboard:
  [{"name": "Woonkamer", "icon": "mdi:sofa",
    "entities": [{"entity_id": "light.stalamp", "name": "Stalamp", "icon": "mdi:floor-lamp"}]}]
"name" en "icon" van een tegel zijn optioneel; standaard komen ze uit Home Assistant.

QuickClient houdt via subscribe_entities live de status bij en roept acties aan
(light.turn_on enz.) over dezelfde websocket. Het paneel met tegels staat in panel.py.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ha_desktop.config import Config
from ha_desktop.hasocket import HaSocket
from ha_desktop.i18n import _

# Aan/uit-schakelbaar; daarna wat je alleen kunt starten. Ook de volgorde binnen een sectie.
TOGGLE_DOMAINS = ("light", "switch", "fan", "input_boolean")
RUN_DOMAINS = ("scene", "script")
DOMAINS = TOGGLE_DOMAINS + RUN_DOMAINS

# Standaardiconen van Home Assistant: (aan, uit).
DEFAULT_ICONS = {
    "light": ("mdi:lightbulb", "mdi:lightbulb-off"),
    "outlet": ("mdi:power-plug", "mdi:power-plug-off"),
    "switch": ("mdi:toggle-switch-variant", "mdi:toggle-switch-variant-off"),
    "fan": ("mdi:fan", "mdi:fan-off"),
    "input_boolean": ("mdi:check-circle-outline", "mdi:close-circle-outline"),
    "scene": ("mdi:palette", "mdi:palette"),
    "script": ("mdi:script-text-play", "mdi:script-text"),
}
# Kleuren van actieve tegels in het standaardthema van Home Assistant.
AMBER, CYAN, BLUE = "#ffc107", "#00bcd4", "#03a9f4"


def domain(entity_id: str) -> str:
    return entity_id.split(".", 1)[0]


def entity_name(entity_id: str, state: dict | None) -> str:
    return str(((state or {}).get("attributes") or {}).get("friendly_name") or entity_id)


def is_on(state: dict | None) -> bool:
    return bool(state) and state.get("state") == "on"


def available(state: dict | None) -> bool:
    # Scènes staan op "unknown" tot ze een keer gestart zijn; die zijn wel bruikbaar.
    return bool(state) and state.get("state") != "unavailable"


def brightness_pct(entity_id: str, state: dict | None) -> int | None:
    """Helderheid 0-100 van een dimbare lamp (0 = uit), of None als hij niet dimbaar is."""
    if domain(entity_id) != "light" or not state:
        return None
    attrs = state.get("attributes") or {}
    modes = attrs.get("supported_color_modes") or []
    if not modes or set(modes) <= {"onoff"}:
        return None
    if state.get("state") != "on":
        return 0
    value = attrs.get("brightness")
    return round(value * 100 / 255) if isinstance(value, (int, float)) else 100


def entity_icon(entity_id: str, state: dict | None, override: str = "") -> str:
    """Icoon van een tegel: zelf gekozen, anders dat uit HA, anders de standaard."""
    attrs = (state or {}).get("attributes") or {}
    if override:
        return override
    if str(attrs.get("icon", "")).startswith("mdi:"):
        return attrs["icon"]
    dom = domain(entity_id)
    key = "outlet" if dom == "switch" and attrs.get("device_class") == "outlet" else dom
    on_icon, off_icon = DEFAULT_ICONS.get(key, ("mdi:help-circle-outline",) * 2)
    return on_icon if is_on(state) else off_icon


def tile_color(entity_id: str, state: dict | None) -> str:
    """Kleur van het icoon; "" als de tegel uit staat."""
    dom = domain(entity_id)
    if dom in RUN_DOMAINS:
        return BLUE
    if not is_on(state):
        return ""
    rgb = (state.get("attributes") or {}).get("rgb_color")
    if dom == "light" and isinstance(rgb, list) and len(rgb) == 3:
        return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(c))) for c in rgb))
    return CYAN if dom == "fan" else AMBER


def state_text(entity_id: str, state: dict | None) -> str:
    if not available(state):
        return _("Unavailable")
    dom = domain(entity_id)
    if dom == "scene":
        return _("Scene")
    if dom == "script":
        return _("Running") if is_on(state) else _("Script")
    if not is_on(state):
        return _("Off")
    pct = brightness_pct(entity_id, state)
    return f"{_('On')} · {pct}%" if pct else _("On")


def sort_key(state: dict) -> tuple[int, str]:
    entity_id = str(state.get("entity_id", ""))
    return DOMAINS.index(domain(entity_id)), entity_name(entity_id, state).lower()


def clean_layout(raw: object) -> list[dict]:
    """De indeling uit config.json, met alleen geldige onderdelen."""
    sections = []
    for section in raw if isinstance(raw, list) else []:
        if not isinstance(section, dict):
            continue
        entities = []
        for entry in section.get("entities") or []:
            if not isinstance(entry, dict) or domain(str(entry.get("entity_id", ""))) not in DOMAINS:
                continue
            entities.append({k: str(v) for k, v in entry.items() if k in ("entity_id", "name", "icon") and v})
        sections.append({"name": str(section.get("name") or ""), "icon": str(section.get("icon") or ""),
                         "entities": entities})
    return sections


def layout_entity_ids(layout: list[dict]) -> list[str]:
    return list(dict.fromkeys(e["entity_id"] for section in layout for e in section["entities"]))


def layout_by_area(states: list[dict], areas: list[dict], devices: list[dict], entities: list[dict]) -> list[dict]:
    """Eén sectie per ruimte, zoals het ruimtedashboard van HA; de rest onder "Overig".

    entities komt uit config/entity_registry/list_for_display (korte sleutels:
    ei = entity_id, ai = ruimte, di = apparaat, ec = categorie, hb = verborgen).
    """
    device_area = {d.get("id"): d.get("area_id") for d in devices}
    registry = {e.get("ei"): e for e in entities}
    by_area: dict[str | None, list[dict]] = {}
    for state in sorted((s for s in states if domain(str(s.get("entity_id", ""))) in DOMAINS), key=sort_key):
        entry = registry.get(state["entity_id"], {})
        if "ec" in entry or entry.get("hb"):
            continue  # configuratie-/diagnose-entiteiten en verborgen entiteiten, net als HA
        area = entry.get("ai") or device_area.get(entry.get("di"))
        by_area.setdefault(area, []).append({"entity_id": state["entity_id"]})
    layout = [{"name": str(a.get("name") or ""), "icon": str(a.get("icon") or ""), "entities": by_area[a["area_id"]]}
              for a in areas if by_area.get(a.get("area_id"))]
    if by_area.get(None):
        layout.append({"name": _("Other"), "icon": "", "entities": by_area[None]})
    return layout


def apply_event(states: dict[str, dict], event: dict) -> bool:
    """Verwerk een subscribe_entities-bericht in states; True als er iets veranderde.

    "a": volledige status (bij start of nieuwe entiteit), "c": verschillen ("+" nieuw
    of gewijzigd, "-" verwijderde attributen), "r": verwijderde entiteiten.
    """
    changed = False
    for entity_id, s in (event.get("a") or {}).items():
        states[entity_id] = {"entity_id": entity_id, "state": s.get("s"), "attributes": dict(s.get("a") or {})}
        changed = True
    for entity_id, diff in (event.get("c") or {}).items():
        current = states.get(entity_id)
        if current is None:
            continue
        plus = diff.get("+") or {}
        if "s" in plus:
            current["state"] = plus["s"]
        current["attributes"].update(plus.get("a") or {})
        for key in (diff.get("-") or {}).get("a") or []:
            current["attributes"].pop(key, None)
        changed = True
    for entity_id in event.get("r") or []:
        changed = states.pop(entity_id, None) is not None or changed
    return changed


class QuickClient(HaSocket):
    # Status van een of meer entiteiten, of de indeling zelf, is veranderd.
    changed = Signal()
    call_failed = Signal(str)

    def __init__(self, config: Config, parent: QObject | None = None) -> None:
        super().__init__(config, parent)
        self.layout: list[dict] = []
        self.entity_ids: list[str] = []
        self.states: dict[str, dict] = {}
        self._sub_id = 0
        self._calls: dict[int, str] = {}

    def configure(self, base_url: str, token: str, layout: list[dict]) -> None:
        """(Her)start met deze instellingen; zonder tegels blijft de verbinding dicht."""
        self.layout = clean_layout(layout)
        entity_ids = layout_entity_ids(self.layout)
        if self._running and (base_url, token, entity_ids) == (self._base_url, self._token, self.entity_ids):
            self.changed.emit()  # alleen namen, iconen of volgorde anders
            return
        self.entity_ids = entity_ids
        self.states.clear()
        if entity_ids and token:
            self.start(base_url, token)
        else:
            self.stop()
            if entity_ids:
                self._set_state("error", _("Quick controls need an access token. Add one in Settings."))
        self.changed.emit()

    def activate(self, entity_id: str) -> None:
        """Zet een lamp of schakelaar aan of uit, of start een scène of script.

        Net als de HA-frontend turn_on/turn_off naar de getoonde status, geen toggle: een
        tweede klik voordat HA de nieuwe status meldt, zet de lamp dan niet meteen weer terug.
        """
        dom = domain(entity_id)
        on = dom in RUN_DOMAINS or not is_on(self.states.get(entity_id))
        self._call(dom, "turn_on" if on else "turn_off", entity_id)

    def set_brightness(self, entity_id: str, pct: int) -> None:
        if pct <= 0:
            self._call("light", "turn_off", entity_id)
        else:
            self._call("light", "turn_on", entity_id, {"brightness_pct": min(100, pct)})

    def _call(self, dom: str, service: str, entity_id: str, data: dict | None = None) -> None:
        if self.state != "connected":
            return
        msg = {"type": "call_service", "domain": dom, "service": service,
               "target": {"entity_id": entity_id}}
        if data:
            msg["service_data"] = data
        self._calls[self._send(msg)] = entity_id

    def _subscribe(self) -> None:
        # Na opnieuw verbinden komt alles opnieuw binnen als "a".
        self.states.clear()
        self._calls.clear()
        self._sub_id = self._send({"type": "subscribe_entities", "entity_ids": self.entity_ids})
        self.changed.emit()

    def _handle(self, msg: dict) -> None:
        kind, msg_id = msg.get("type"), msg.get("id")
        if kind == "result" and msg_id == self._sub_id:
            if msg.get("success"):
                self._subscribed()
            else:
                err = (msg.get("error") or {}).get("message") or _("unknown error")
                self._fail(_("Loading quick controls failed: {error}").format(error=err))
        elif kind == "result" and msg_id in self._calls:
            entity_id = self._calls.pop(msg_id)
            if not msg.get("success"):
                err = (msg.get("error") or {}).get("message") or _("unknown error")
                name = entity_name(entity_id, self.states.get(entity_id))
                self.call_failed.emit(_("Couldn't control {name}: {error}").format(name=name, error=err))
        elif kind == "event" and msg_id == self._sub_id:
            if apply_event(self.states, msg.get("event") or {}):
                self.changed.emit()

    def sections(self) -> list[tuple[dict, list[dict]]]:
        """Secties met de tegels waarvan de status bekend is; lege secties vallen weg."""
        result = []
        for section in self.layout:
            entries = [e for e in section["entities"] if e["entity_id"] in self.states]
            if entries:
                result.append((section, entries))
        return result
