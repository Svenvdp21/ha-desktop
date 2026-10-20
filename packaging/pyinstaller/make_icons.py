"""Maakt build/icon.png (1024 px) en build/icon.ico uit het SVG-logo."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SVG = ROOT / "ha_desktop/data/com.nordicnode.HADesktop.svg"
OUT = ROOT / "build"

app = QGuiApplication(sys.argv[:1])
OUT.mkdir(exist_ok=True)
image = QImage(1024, 1024, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
painter = QPainter(image)
QSvgRenderer(str(SVG)).render(painter)
painter.end()
image.save(str(OUT / "icon.png"))

Image.open(OUT / "icon.png").save(
    OUT / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
)
print("iconen gemaakt in", OUT)
