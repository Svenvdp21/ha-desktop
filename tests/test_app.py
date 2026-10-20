"""Draai met: QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fake_ha import TOKEN, WEBHOOK, FakeHA  # noqa: E402
from ha_desktop.config import Config, normalize_url  # noqa: E402
from ha_desktop.haapi import HaApi  # noqa: E402
from ha_desktop.notifier import notification_target  # noqa: E402
from ha_desktop.push import PushClient, websocket_url  # noqa: E402

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


def call(fn, *args, timeout=5000):
    loop = QEventLoop()
    box = []
    fn(*args, lambda r: (box.append(r), loop.quit()))
    QTimer.singleShot(timeout, loop.quit)
    loop.exec()
    if not box:
        raise AssertionError("time-out")
    return box[0]


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
        self.assertIn("geweigerd", refused.error)

    def test_register(self):
        bad = call(self.api.register_device, self.ha.url, "fout")
        self.assertIn("ongeldig", bad.error)
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

    def test_push_bad_token_and_webhook(self):
        push = PushClient(self.config)
        _keep.append(push)
        push.start(self.ha.url, "fout", WEBHOOK)
        while push.state != "error":
            wait_for(push.status_changed)
        self.assertIn("Token", push.detail)
        push.start(self.ha.url, TOKEN, "verkeerd")
        while push.state != "error":
            wait_for(push.status_changed)
        self.assertIn("Webhook ID not found", push.detail)
        push.stop()


if __name__ == "__main__":
    unittest.main()
