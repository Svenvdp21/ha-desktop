"""Material Design Icons: dezelfde iconen als Home Assistant ("mdi:sofa" enz.).

Lettertype en tekenlijst komen uit @mdi/font 7.4.47 (Apache 2.0), zie data/mdi.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap

_DIR = Path(__file__).resolve().parent / "data" / "mdi"


@lru_cache(maxsize=1)
def _chars() -> dict[str, str]:
    chars = {}
    for line in (_DIR / "icons.txt").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, code = line.split()
            chars[name] = chr(int(code, 16))
    return chars


@lru_cache(maxsize=1)
def _family() -> str:
    font_id = QFontDatabase.addApplicationFont(str(_DIR / "materialdesignicons-webfont.ttf"))
    families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
    return families[0] if families else ""


def normalize(text: str) -> str:
    """"sofa", "mdi:sofa" of " MDI:Sofa " -> "mdi:sofa"; leeg blijft leeg."""
    name = text.strip().lower().removeprefix("mdi:").strip()
    return f"mdi:{name}" if name else ""


def exists(name: str) -> bool:
    return name.startswith("mdi:") and name[4:] in _chars()


def draw(painter: QPainter, rect: QRectF, name: str, color: QColor) -> None:
    char = _chars().get(name.removeprefix("mdi:"))
    family = _family()
    if not char or not family:
        return
    font = QFont(family)
    font.setPixelSize(max(1, round(rect.height())))
    painter.save()
    painter.setFont(font)
    painter.setPen(color)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, char)
    painter.restore()


def icon(name: str, color: QColor, size: int = 48) -> QIcon:
    if not exists(name):
        return QIcon()
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw(painter, QRectF(0, 0, size, size), name, color)
    painter.end()
    return QIcon(pixmap)
