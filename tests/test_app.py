"""Draai met: QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QEventLoop, QPoint, QRect, QSize, QTimer, Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QToolButton  # noqa: E402

from fake_ha import REGISTRY, STATES, TOKEN, WEBHOOK, FakeHA  # noqa: E402
import ast  # noqa: E402
from unittest import mock  # noqa: E402

from ha_desktop import designer as designer_module, i18n, icons, kwin, panel as panel_module  # noqa: E402
from ha_desktop import settings as settings_module  # noqa: E402
from ha_desktop.config import Config, normalize_url  # noqa: E402
from ha_desktop.haapi import HaApi, Result  # noqa: E402
from ha_desktop.hasocket import websocket_url  # noqa: E402
from ha_desktop.notifier import notification_target  # noqa: E402
from ha_desktop.designer import ENTITY, LayoutEditor  # noqa: E402
from ha_desktop.onboarding import Onboarding  # noqa: E402
from ha_desktop.panel import GAP, QuickPanel, context_panel, panel_position  # noqa: E402
from ha_desktop.push import PushClient  # noqa: E402
from ha_desktop.settings import SettingsDialog  # noqa: E402
from ha_desktop.quick import (  # noqa: E402
    AMBER, BLUE, CYAN, DEFAULT_ICONS, QuickClient, apply_event, brightness_pct, clean_layout,
    entity_icon, is_on, layout_by_area, layout_entity_ids, state_text, tile_color,
)

app = QApplication.instance() or QApplication([])
# Qt-objecten niet midden in de event-loop laten opruimen door Python's GC.
_keep = []


def wait_for(signal_or_check, timeout=5000):
    """Wacht op een signaal en geef de argumenten terug."""
    loop = QEventLoop()
    got = []

    def hit(*args):
        got.append(args)
        loop.quit()

    signal_or_check.connect(hit)
    QTimer.singleShot(timeout, loop.quit)
    loop.exec()
    signal_or_check.disconnect(hit)
    if not got:
        raise AssertionError("time-out")
    return got[0]


def wait_until(check, timeout=5000):
    """Laat de event-loop draaien tot check() waar is."""
    loop = QEventLoop()
    timer = QTimer(interval=10)
    timer.timeout.connect(lambda: check() and loop.quit())
    QTimer.singleShot(timeout, loop.quit)
    timer.start()
    loop.exec()
    timer.stop()
    if not check():
        raise AssertionError("time-out")


def call(fn, *args, timeout=5000):
    loop = QEventLoop()
    box = []
    fn(*args, lambda r: (box.append(r), loop.quit()))
    QTimer.singleShot(timeout, loop.quit)
    loop.exec()
    if not box:
        raise AssertionError("time-out")
    return box[0]


i18n.set_language("en")
PACKAGE = Path(__file__).resolve().parent.parent / "ha_desktop"


class TranslationTests(unittest.TestCase):
    def _strings(self):
        """Alle letterlijke teksten in _("...") en N_("...") in de broncode."""
        found = {}
        for path in PACKAGE.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id in ("_", "N_") and node.args
                        and isinstance(node.args[0], ast.Constant)):
                    found[node.args[0].value] = path.name
        return found

    def test_every_string_has_dutch(self):
        from ha_desktop.translations import NL
        missing = {t: f for t, f in self._strings().items() if t not in NL}
        self.assertEqual(missing, {}, "Ontbrekende Nederlandse vertalingen")

    def test_placeholders_match(self):
        from string import Formatter
        from ha_desktop.translations import NL
        names = lambda t: {f for _, f, _, _ in Formatter().parse(t) if f}
        for en, nl in NL.items():
            self.assertEqual(names(en), names(nl), en)

    def test_no_unused_translations(self):
        from ha_desktop.translations import NL
        unused = set(NL) - set(self._strings())
        self.assertEqual(unused, set())

    def test_switch_language(self):
        try:
            i18n.set_language("nl")
            self.assertEqual(i18n._("Connect"), "Verbinden")
            with self.assertRaisesRegex(ValueError, "geldig adres"):
                normalize_url("http://")
        finally:
            i18n.set_language("en")
        self.assertEqual(i18n._("Connect"), "Connect")


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HA_DESKTOP_CONFIG_DIR"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_normalize(self):
        self.assertEqual(normalize_url("homeassistant.local:8123"),
                         ["https://homeassistant.local:8123", "http://homeassistant.local:8123"])
        self.assertEqual(normalize_url(" http://10.0.0.5:8123/lovelace/0 "), ["http://10.0.0.5:8123"])
        self.assertEqual(normalize_url("https://abc.ui.nabu.casa/"), ["https://abc.ui.nabu.casa"])
        for bad in ["", "ftp://x", "http://", "http://host:99999"]:
            with self.assertRaises(ValueError):
                normalize_url(bad)

    def test_roundtrip_and_corrupt(self):
        c = Config(server_url="http://x:8123", notifications=True)
        c.trust_host("x")
        c.save()
        loaded = Config.load()
        self.assertEqual(loaded.server_url, "http://x:8123")
        self.assertTrue(loaded.trusts("x"))
        self.assertEqual(loaded.device_id, c.device_id)
        self.assertEqual(os.stat(Path(self.tmp.name) / "config.json").st_mode & 0o777, 0o600)
        (Path(self.tmp.name) / "config.json").write_text("{kapot")
        self.assertEqual(Config.load().server_url, "")
        self.assertTrue((Path(self.tmp.name) / "config.json.bak").exists())

    def test_linux_paths_unchanged(self):
        """Bestaande Linux-installaties mogen hun instellingen en login nooit kwijtraken."""
        from unittest import mock

        from ha_desktop import config
        home = Path.home()
        env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_", "HA_DESKTOP_"))}
        with mock.patch.object(config.sys, "platform", "linux"), mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(config.config_dir(), home / ".config/ha-desktop")
            self.assertEqual(config.data_dir(), home / ".local/share/ha-desktop")
            self.assertEqual(config.cache_dir(), home / ".cache/ha-desktop")

    def test_spec_version_matches(self):
        """COPR bouwt uit de spec; die moet dezelfde versie hebben als de app."""
        import re

        from ha_desktop import __version__
        spec = (PACKAGE.parent / "packaging/ha-desktop.spec").read_text()
        self.assertEqual(re.search(r"^Version:\s*(\S+)", spec, re.M).group(1), __version__)
        self.assertIn(f"- {__version__}-1", spec, "changelog-regel voor deze versie ontbreekt")

    def test_ws_url_and_target(self):
        self.assertEqual(websocket_url("https://a.b"), "wss://a.b/api/websocket")
        self.assertEqual(websocket_url("http://a:8123"), "ws://a:8123/api/websocket")
        self.assertEqual(notification_target({"data": {"url": "/lovelace/cams"}}), "/lovelace/cams")
        self.assertEqual(notification_target({"data": {"clickAction": "/x"}}), "/x")
        self.assertEqual(notification_target({"data": None}), "")


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HA_DESKTOP_CONFIG_DIR"] = self.tmp.name
        self.ha = FakeHA()
        self.config = Config(server_url=self.ha.url)
        self.api = HaApi(self.config)
        _keep.extend([self.ha, self.api])

    def tearDown(self):
        self.tmp.cleanup()

    def test_probe(self):
        self.assertTrue(call(self.api.probe, self.ha.url).ok)
        bad = call(self.api.probe, self.ha.url + "/nope")
        self.assertFalse(bad.ok)
        refused = call(self.api.probe, "http://127.0.0.1:1")
        self.assertIn("refused", refused.error)

    def test_register(self):
        bad = call(self.api.register_device, self.ha.url, "fout")
        self.assertIn("invalid", bad.error)
        good = call(self.api.register_device, self.ha.url, TOKEN)
        self.assertEqual(good.data["webhook_id"], WEBHOOK)
        reg = self.ha.registrations[0]
        self.assertTrue(reg["app_data"]["push_websocket_channel"])
        self.assertEqual(reg["device_id"], self.config.device_id)

    def test_push_flow(self):
        push = PushClient(self.config)
        _keep.append(push)
        received = []
        push.notification.connect(received.append)
        push.start(self.ha.url, TOKEN, WEBHOOK)
        wait_for(self.ha.subscribed)
        if push.state != "connected":
            wait_for(push.status_changed)
        self.assertEqual(push.state, "connected")

        self.ha.push("Deurbel", "Er staat iemand voor de deur", {"url": "/lovelace/cams"}, confirm_id="c1")
        self.assertEqual(wait_for(self.ha.confirmed)[0], "c1")
        app.processEvents()
        self.assertEqual(received[0]["message"], "Er staat iemand voor de deur")

        self.ha.push("", "clear_notification")
        loop = QEventLoop()
        QTimer.singleShot(200, loop.quit)
        loop.exec()

        # Verbinding valt weg -> automatisch opnieuw verbinden.
        self.ha.drop_clients()
        wait_for(self.ha.subscribed, timeout=8000)
        push.stop()
        self.assertEqual(len(received), 1)

    def test_push_retries_while_ha_starts(self):
        # Vlak na een HA-herstart kent HA mobile_app nog niet; de client moet blijven proberen.
        self.ha.mobile_app_loaded = False
        push = PushClient(self.config)
        _keep.append(push)
        states = []
        push.status_changed.connect(lambda state, detail: states.append(state))
        push.start(self.ha.url, TOKEN, WEBHOOK)
        while "disconnected" not in states:
            wait_for(push.status_changed)
        self.ha.mobile_app_loaded = True
        while push.state != "connected":
            wait_for(push.status_changed)
        self.assertNotIn("error", states)
        push.stop()

    def test_push_bad_token_and_webhook(self):
        push = PushClient(self.config)
        _keep.append(push)
        push.start(self.ha.url, "fout", WEBHOOK)
        while push.state != "error":
            wait_for(push.status_changed)
        self.assertIn("token", push.detail)
        push.start(self.ha.url, TOKEN, "verkeerd")
        while push.state != "error":
            wait_for(push.status_changed)
        self.assertIn("Webhook ID not found", push.detail)
        push.stop()


class QuickHelperTests(unittest.TestCase):
    def test_apply_event(self):
        states = {}
        self.assertTrue(apply_event(states, {"a": {"light.x": {"s": "on", "a": {"brightness": 255}}}}))
        self.assertTrue(apply_event(states, {"c": {"light.x": {"+": {"s": "off", "a": {"friendly_name": "X"}},
                                                               "-": {"a": ["brightness"]}}}}))
        self.assertEqual(states["light.x"]["state"], "off")
        self.assertEqual(states["light.x"]["attributes"], {"friendly_name": "X"})
        self.assertFalse(apply_event(states, {"c": {"light.onbekend": {"+": {"s": "on"}}}}))
        self.assertTrue(apply_event(states, {"r": ["light.x"]}))
        self.assertFalse(apply_event(states, {"r": ["light.x"]}))
        self.assertEqual(states, {})

    def test_brightness(self):
        dim = {"supported_color_modes": ["color_temp", "xy"]}
        self.assertEqual(brightness_pct("light.a", {"state": "on", "attributes": {**dim, "brightness": 128}}), 50)
        self.assertEqual(brightness_pct("light.a", {"state": "on", "attributes": dim}), 100)
        self.assertEqual(brightness_pct("light.a", {"state": "off", "attributes": dim}), 0)
        self.assertIsNone(brightness_pct("light.a", {"state": "on", "attributes": {"supported_color_modes": ["onoff"]}}))
        self.assertIsNone(brightness_pct("light.a", {"state": "unavailable", "attributes": {}}))
        self.assertIsNone(brightness_pct("switch.a", {"state": "on", "attributes": dim}))

    def test_icons_and_colors(self):
        on, off = {"state": "on", "attributes": {}}, {"state": "off", "attributes": {}}
        self.assertEqual(entity_icon("light.a", on), "mdi:lightbulb")
        self.assertEqual(entity_icon("light.a", off), "mdi:lightbulb-off")
        lamp = {"state": "off", "attributes": {"icon": "mdi:floor-lamp"}}
        self.assertEqual(entity_icon("light.a", lamp), "mdi:floor-lamp")
        self.assertEqual(entity_icon("light.a", lamp, "mdi:sofa"), "mdi:sofa")
        self.assertEqual(entity_icon("switch.a", {"state": "off", "attributes": {"device_class": "outlet"}}),
                         "mdi:power-plug-off")
        # Elk standaardicoon moet in het meegeleverde lettertype staan.
        for name in [*(i for pair in DEFAULT_ICONS.values() for i in pair), "mdi:cog", "mdi:close"]:
            self.assertTrue(icons.exists(name), name)
        self.assertFalse(icons.exists("mdi:bestaat-niet"))
        self.assertEqual(icons.normalize(" MDI:Floor-Lamp "), "mdi:floor-lamp")
        self.assertEqual(icons.normalize(""), "")
        self.assertFalse(icons.icon("mdi:sofa", QColor("red")).isNull())

        self.assertEqual(tile_color("light.a", {"state": "on", "attributes": {"rgb_color": [255, 0, 16]}}), "#ff0010")
        self.assertEqual(tile_color("light.a", on), AMBER)
        self.assertEqual(tile_color("light.a", off), "")
        self.assertEqual(tile_color("fan.a", on), CYAN)
        self.assertEqual(tile_color("scene.a", {"state": "unknown"}), BLUE)
        dimmed = {"state": "on", "attributes": {"supported_color_modes": ["brightness"], "brightness": 128}}
        self.assertEqual(state_text("light.a", dimmed), "On · 50%")
        self.assertEqual(state_text("switch.a", off), "Off")
        self.assertEqual(state_text("switch.a", {"state": "unavailable"}), "Unavailable")
        self.assertEqual(state_text("scene.a", {"state": "unknown"}), "Scene")

    def test_layout_helpers(self):
        raw = [{"name": "A", "entities": [{"entity_id": "light.a", "name": ""}, {"entity_id": "sensor.x"}, "rommel",
                                          {"entity_id": "light.a"}]}, "rommel"]
        layout = clean_layout(raw)
        self.assertEqual(layout, [{"name": "A", "icon": "", "entities": [{"entity_id": "light.a"}] * 2}])
        self.assertEqual(layout_entity_ids(layout), ["light.a"])
        self.assertEqual(clean_layout(None), [])

    def test_layout_by_area(self):
        states = [{"entity_id": e, **s} for e, s in STATES.items()]
        display = REGISTRY["config/entity_registry/list_for_display"]["entities"]
        layout = layout_by_area(states, REGISTRY["config/area_registry/list"],
                                REGISTRY["config/device_registry/list"], display)
        self.assertEqual(layout, [
            # light.woonkamer via zijn apparaat; switch.led (configuratie) en light.verborgen vallen weg.
            {"name": "Woonkamer", "icon": "mdi:sofa", "entities": [{"entity_id": "light.woonkamer"},
                                                                   {"entity_id": "switch.tv"}]},
            {"name": "Keuken", "icon": "mdi:fridge", "entities": [{"entity_id": "light.gang"}]},
            {"name": "Other", "icon": "", "entities": [{"entity_id": "scene.film"}]},
        ])

    def test_panel_position(self):
        size = QSize(340, 300)
        # Windows: taakbalk onderaan; paneel erboven (tegen de taakbalk), rechts uitgelijnd met het icoon.
        area = QRect(0, 0, 1920, 1040)
        self.assertEqual(panel_position(QRect(1800, 1050, 24, 24), size, area).toTuple(), (1483, 740))
        # Balk bovenaan (macOS, GNOME): eronder.
        area = QRect(0, 32, 1920, 1048)
        self.assertEqual(panel_position(QRect(1700, 4, 24, 24), size, area).toTuple(), (1383, 35))
        # Nooit buiten het scherm.
        pos = panel_position(QRect(10, 1050, 24, 24), size, QRect(0, 0, 1920, 1040))
        self.assertEqual(pos.x(), 0)

    def test_kwin_script(self):
        script = kwin.script('Snel — "x"')
        self.assertIn(f'const CAPTION = "Snel \\u2014 \\"x\\"", PID = {os.getpid()}, GAP = 8;', script)
        self.assertNotIn("__", script)

    def test_where_right_click_shows_panel(self):
        cases = [({"XDG_CURRENT_DESKTOP": "GNOME"}, False),
                 ({"XDG_CURRENT_DESKTOP": "KDE", "KDE_SESSION_VERSION": "5", "WAYLAND_DISPLAY": "wayland-0"}, False),
                 ({"XDG_CURRENT_DESKTOP": "KDE", "KDE_SESSION_VERSION": "6", "WAYLAND_DISPLAY": "wayland-0"}, True)]
        for env, expected in cases:
            with mock.patch.dict(os.environ, env), mock.patch.object(sys, "platform", "linux"):
                self.assertEqual(context_panel(), expected, env)
                self.assertFalse(kwin.is_plasma6() and env["KDE_SESSION_VERSION"] == "5")
        with mock.patch.object(sys, "platform", "win32"):
            self.assertTrue(context_panel())



class FakeTokens:
    def __init__(self, token=""):
        self.stored = {"": token} if token else {}

    def get(self, server):
        return self.stored.get(server, self.stored.get("", ""))

    def set(self, server, token):
        self.stored[server] = token


class QuickTests(unittest.TestCase):
    LAYOUT = [
        {"name": "Woonkamer", "icon": "mdi:sofa",
         "entities": [{"entity_id": "light.woonkamer"}, {"entity_id": "switch.tv", "name": "Tv"}]},
        {"name": "", "icon": "", "entities": [{"entity_id": "scene.film"}, {"entity_id": "light.weg"}]},
    ]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HA_DESKTOP_CONFIG_DIR"] = self.tmp.name
        self.ha = FakeHA()
        self.config = Config(server_url=self.ha.url)
        self.api = HaApi(self.config)
        self.client = QuickClient(self.config)
        self.calls = []
        self.ha.called.connect(self.calls.append)
        _keep.extend([self.ha, self.api, self.client])

    def tearDown(self):
        self.client.stop()
        self.tmp.cleanup()

    def _connect(self):
        self.client.configure(self.ha.url, TOKEN, self.LAYOUT)
        wait_until(lambda: self.client.state == "connected" and "scene.film" in self.client.states)

    def test_get_states(self):
        self.assertIn("invalid", call(self.api.get_states, self.ha.url, "fout").error)
        good = call(self.api.get_states, self.ha.url, TOKEN)
        self.assertIn("light.woonkamer", [s["entity_id"] for s in good.data["states"]])

    def test_ws_request(self):
        requests = [{"type": "config/area_registry/list"}, {"type": "config/device_registry/list"}]
        good = call(self.api.ws_request, self.ha.url, TOKEN, requests)
        self.assertEqual(good.data["results"][1], [{"id": "dev1", "area_id": "woonkamer"}])
        self.assertIn("rejected", call(self.api.ws_request, self.ha.url, "fout", requests).error)
        self.assertIn("Unknown command", call(self.api.ws_request, self.ha.url, TOKEN, [{"type": "x"}]).error)
        self.assertIn("refused", call(self.api.ws_request, "http://127.0.0.1:1", TOKEN, requests).error)

    def test_client_flow(self):
        self._connect()
        states = self.client.states
        self.assertEqual(set(states), {"light.woonkamer", "switch.tv", "scene.film"})
        self.assertEqual([[e["entity_id"] for e in entries] for _s, entries in self.client.sections()],
                         [["light.woonkamer", "switch.tv"], ["scene.film"]])

        self.client.activate("switch.tv")
        wait_until(lambda: is_on(states["switch.tv"]))
        self.assertEqual(self.calls[-1], {"domain": "switch", "service": "turn_on", "entity_id": "switch.tv"})

        # Twee klikken voordat HA de nieuwe status meldt: niet aan en meteen weer uit.
        self.client.activate("switch.tv")
        self.client.activate("switch.tv")
        wait_until(lambda: len(self.calls) == 3 and not is_on(states["switch.tv"]))
        self.assertEqual([c["service"] for c in self.calls[1:]], ["turn_off", "turn_off"])

        self.client.set_brightness("light.woonkamer", 30)
        wait_until(lambda: brightness_pct("light.woonkamer", states["light.woonkamer"]) == 30)
        self.client.set_brightness("light.woonkamer", 0)
        wait_until(lambda: not is_on(states["light.woonkamer"]))
        self.assertNotIn("brightness", states["light.woonkamer"]["attributes"])
        self.assertEqual(self.calls[-1]["service"], "turn_off")

        self.client.activate("scene.film")
        wait_until(lambda: states["scene.film"]["state"] != "unknown")
        self.assertEqual(self.calls[-1]["service"], "turn_on")

        self.client.activate("light.weg")
        self.assertIn("light.weg", wait_for(self.client.call_failed)[0])

        self.ha.remove_entity("switch.tv")
        wait_until(lambda: "switch.tv" not in states)

        # Verbinding valt weg -> opnieuw verbinden en alles opnieuw ophalen.
        self.ha.drop_clients()
        wait_until(lambda: self.client.state != "connected")
        wait_until(lambda: self.client.state == "connected" and "scene.film" in self.client.states, 8000)

        # Alleen namen anders: niet opnieuw verbinden.
        subs = len(self.ha.entity_subs)
        renamed = [{**self.LAYOUT[0], "name": "Huiskamer"}, self.LAYOUT[1]]
        self.client.configure(self.ha.url, TOKEN, renamed)
        self.assertEqual(len(self.ha.entity_subs), subs)
        self.assertEqual(self.client.layout[0]["name"], "Huiskamer")

    def test_client_without_token_or_entities(self):
        self.client.configure(self.ha.url, "", self.LAYOUT)
        self.assertEqual(self.client.state, "error")
        self.assertIn("token", self.client.detail)
        self.client.configure(self.ha.url, "fout", self.LAYOUT)
        wait_until(lambda: self.client.state == "error" and "rejected" in self.client.detail)
        self.client.configure(self.ha.url, TOKEN, [])
        self.assertEqual(self.client.state, "disconnected")
        self.assertEqual(self.client.states, {})

    def test_settings_apply_only_on_save(self):
        config = Config(server_url=self.ha.url, quick_layout=self.LAYOUT)
        push = PushClient(config)
        dialog = SettingsDialog(config, self.api, FakeTokens(), push, True)
        _keep.extend([push, dialog])
        changed = []
        dialog.quick_changed.connect(lambda: changed.append(True))
        dialog._quick = []
        dialog.close_to_tray.setChecked(False)
        dialog.notify_enabled.setChecked(True)
        with mock.patch.object(settings_module, "set_autostart"):
            dialog._save()  # zonder token mislukt dat; annuleren laat alles dan zoals het was
            self.assertEqual((config.quick_layout, config.close_to_tray, changed), (self.LAYOUT, True, []))
            dialog.notify_enabled.setChecked(False)
            dialog._save()
        self.assertEqual((config.quick_layout, config.close_to_tray, changed), ([], False, [True]))
        self.assertEqual(Config.load().quick_layout, [])

    def test_new_server_forgets_layout(self):
        config = Config(server_url="http://oud.example", quick_layout=self.LAYOUT)
        onboarding = Onboarding(config, self.api, FakeTokens())
        _keep.append(onboarding)
        onboarding._probed(self.ha.url, Result(True))
        self.assertEqual((config.server_url, config.quick_layout), (self.ha.url, []))

    def test_panel(self):
        panel = QuickPanel(self.client, mode="window")
        _keep.append(panel)
        panel.popup(QRect(10, 10, 1, 1))
        self.assertIn("Settings", panel.message.text())
        self._connect()
        self.assertEqual([t.entity_id for t in panel.tiles], ["light.woonkamer", "switch.tv", "scene.film"])
        self.assertEqual(len(panel._sections), 2)
        self.assertTrue(panel.message.isHidden())
        light, tv, scene = panel.tiles
        self.assertEqual((light.name, tv.name, scene.name), ("Woonkamer", "Tv", "Film kijken"))
        self.assertTrue(light._dimmable())
        self.assertFalse(tv._dimmable())

        # Andere sectienaam: de kop volgt, ook als de tegels dezelfde blijven.
        self.client.configure(self.ha.url, TOKEN, [{**self.LAYOUT[0], "name": "Huiskamer"}, self.LAYOUT[1]])
        self.assertIn("Huiskamer", [label.text() for label in panel.content.findChildren(QLabel)])
        light, tv, scene = panel.tiles

        QTest.mouseClick(tv, Qt.MouseButton.LeftButton)
        wait_until(lambda: is_on(self.client.states["switch.tv"]))

        # Dubbelklik (zoals Qt hem echt aflevert): één keer schakelen.
        calls = len(self.calls)
        QTest.mouseClick(tv, Qt.MouseButton.LeftButton)
        QTest.mouseDClick(tv, Qt.MouseButton.LeftButton)
        QTest.mouseRelease(tv, Qt.MouseButton.LeftButton)
        wait_until(lambda: not is_on(self.client.states["switch.tv"]))
        QTest.qWait(100)
        self.assertEqual(len(self.calls), calls + 1)

        # Slepen dimt in plaats van schakelen.
        x = light.width() * 4 // 5
        QTest.mousePress(light, Qt.MouseButton.LeftButton, pos=QPoint(5, 20))
        QTest.mouseMove(light, QPoint(x, 20))
        QTest.mouseRelease(light, Qt.MouseButton.LeftButton, pos=QPoint(x, 20))
        expected = round(x * 100 / light.width())
        wait_until(lambda: self.calls and self.calls[-1].get("brightness_pct") == expected)
        wait_until(lambda: brightness_pct("light.woonkamer", self.client.states["light.woonkamer"]) == expected)
        self.assertIsNone(light._dim)

        light.setFocus()
        QTest.keyClick(light, Qt.Key.Key_Left)
        wait_until(lambda: self.calls[-1].get("brightness_pct") == expected - 10)
        wait_until(lambda: light._dim is None)

        # De nieuwe helderheid blijft staan tot HA voor déze lamp iets meldt, of tot de wachttijd om is.
        light._preview(55)
        light._dim_sent_at = light._light_state()
        self.client.changed.emit()
        self.assertEqual(light._dim, 55)
        self.client.states["light.woonkamer"]["attributes"]["brightness"] = 140
        self.client.changed.emit()
        self.assertIsNone(light._dim)
        light._preview(30)
        light._dim_sent_at = light._light_state()
        light._dim_hold.start(10)
        wait_until(lambda: light._dim is None)

        QTest.mouseClick(scene, Qt.MouseButton.LeftButton)
        wait_until(lambda: self.calls[-1]["entity_id"] == "scene.film")

        # Onderin wat anders in het tray-menu staat.
        requested = []
        panel.open_requested.connect(lambda: requested.append("open"))
        panel.quit_requested.connect(lambda: requested.append("quit"))
        buttons = {button.text(): button for button in panel.findChildren(QToolButton)}
        buttons["Open"].click()
        self.assertFalse(panel.isVisible())
        buttons["Quit"].click()
        self.assertEqual(requested, ["open", "quit"])

    def test_panel_popup_size_and_place(self):
        panel = QuickPanel(self.client, mode="popup")
        _keep.append(panel)
        self.assertEqual(panel.width(), panel_module.WIDTH + 2 * panel.frameWidth())
        panel._fit(scrolling=True)
        self.assertGreater(panel.width(), panel_module.WIDTH + 2 * panel.frameWidth())

        # Taakbalk onderaan: het paneel blijft er tegenaan staan als het groeit (tegels geladen).
        area = (panel.screen() or app.primaryScreen()).availableGeometry()
        anchor = QRect(area.right() - 30, area.bottom() - 10, 24, 24)
        panel.popup(anchor)
        small, target = panel.height(), anchor.top() - GAP - 1
        self.assertLessEqual(abs(panel.geometry().bottom() - target), 2)  # offscreen verschuift de eerste keer
        self._connect()
        self.assertGreater(panel.height(), small)
        self.assertEqual(panel.geometry().bottom(), target)
        panel.close()

    def test_panel_toggle(self):
        panel = QuickPanel(self.client, mode="window")
        _keep.append(panel)
        anchor = QRect(10, 10, 1, 1)
        panel.toggle(anchor)
        self.assertTrue(panel.isVisible())
        panel.toggle(anchor)
        self.assertFalse(panel.isVisible())
        # De klik op het icoon die het paneel net liet sluiten (focus kwijt), opent het niet weer.
        panel.show()
        panel.hide()
        panel.toggle(anchor)
        self.assertFalse(panel.isVisible())
        panel._hidden_at -= 1
        panel.toggle(anchor)
        self.assertTrue(panel.isVisible())
        panel.close()

    def test_panel_kwin_mode(self):
        panel = QuickPanel(self.client, mode="kwin")
        _keep.append(panel)
        self.assertTrue(panel.windowFlags() & Qt.WindowType.FramelessWindowHint)
        placed = []
        with mock.patch.object(panel_module.kwin, "place", placed.append):
            panel.popup(QRect())
        self.assertEqual(placed, [panel.windowTitle()])
        panel.close()

    def test_editor(self):
        tokens = FakeTokens()
        layout = [{"name": "Woonkamer", "icon": "mdi:sofa", "entities": [{"entity_id": "switch.tv"}]}]
        editor = LayoutEditor(self.config, self.api, tokens, layout)
        _keep.append(editor)
        tree = editor.tree
        section = tree.topLevelItem(0)
        self.assertFalse(editor.token_row.isHidden())
        self.assertEqual(section.child(0).text(0), "switch.tv")  # naam pas bekend na laden
        self.assertFalse(editor.by_area.isEnabled())

        editor.token.setText(TOKEN)
        self.assertFalse(editor.token_saved)
        editor.load()
        wait_until(editor.by_area.isEnabled)
        self.assertEqual(tokens.get(self.ha.url), TOKEN)
        self.assertTrue(editor.token_saved)
        self.assertEqual(section.child(0).text(0), "Stopcontact tv")
        items = {editor.list.item(i).data(Qt.ItemDataRole.UserRole): editor.list.item(i)
                 for i in range(editor.list.count())}
        self.assertNotIn("sensor.temperatuur", items)
        self.assertEqual(items["switch.tv"].checkState(), Qt.CheckState.Checked)

        # Aanvinken voegt toe aan de gekozen sectie, uitvinken haalt weg.
        tree.setCurrentItem(section)
        items["light.gang"].setCheckState(Qt.CheckState.Checked)
        items["switch.tv"].setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual([section.child(i).data(0, ENTITY) for i in range(section.childCount())], ["light.gang"])

        # Eigen naam en icoon; de naam uit HA terugzetten wist de eigen naam.
        tile = section.child(0)
        tile.setText(0, "Gang!")
        tile.setText(1, " Floor-Lamp ")
        self.assertEqual(editor.layout()[0]["entities"], [{"entity_id": "light.gang", "name": "Gang!",
                                                          "icon": "mdi:floor-lamp"}])
        tile.setText(0, "Gang")
        self.assertNotIn("name", editor.layout()[0]["entities"][0])

        # Nieuwe sectie, omhoog, en een tegel die buiten een sectie belandt.
        editor._add_section()
        tree.setCurrentItem(tree.topLevelItem(1))
        editor._move(-1)
        self.assertEqual([s["name"] for s in editor.layout()], ["New section", "Woonkamer"])
        tree.addTopLevelItem(tree.topLevelItem(1).takeChild(0))
        tree.normalize()
        self.assertEqual([len(s["entities"]) for s in editor.layout()], [0, 1])

        with mock.patch.object(designer_module.QMessageBox, "question",
                               return_value=designer_module.QMessageBox.StandardButton.Yes):
            editor.by_area.click()
        wait_until(lambda: editor.by_area.isEnabled() and tree.topLevelItemCount() == 3)
        self.assertEqual([s["name"] for s in editor.layout()], ["Woonkamer", "Keuken", "Other"])
        self.assertEqual(items["light.gang"].checkState(), Qt.CheckState.Checked)
        self.assertEqual(items["switch.led"].checkState(), Qt.CheckState.Unchecked)


if __name__ == "__main__":
    unittest.main()
