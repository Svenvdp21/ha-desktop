"""Snelbedieningspaneel: secties met tegels in de stijl van Home Assistant.

Een tegel toont icoon, naam en status. Klikken schakelt; een dimbare lamp dim je
door horizontaal over de tegel te slepen (of met pijltje links/rechts).

Waar het paneel verschijnt (panel_mode):
- "popup": Windows, macOS en X11. Naast het tray-icoon; sluit als je ernaast klikt.
- "kwin": KDE Plasma op Wayland. Randloos venster dat KWin bij de muis zet (kwin.py);
  sluit als het de focus verliest.
- "window": andere Wayland-desktops. Een app mag daar geen vensterpositie kiezen
  (en geen popup zonder eigen venster openen), dus een klein gewoon venster.

Waar het kan (context_panel) is het paneel ook het rechtsklikmenu van het tray-icoon;
daarom staan Openen, Instellingen en Afsluiten onderin.
"""

from __future__ import annotations

import os
import sys
import time
from functools import lru_cache

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QKeySequence, QPainter, QPainterPath, QPalette, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ha_desktop import APP_NAME, icons, kwin
from ha_desktop.i18n import _
from ha_desktop.onboarding import _wrap
from ha_desktop.quick import (
    QuickClient,
    available,
    brightness_pct,
    entity_icon,
    entity_name,
    state_text,
    tile_color,
)
from ha_desktop.resources import app_icon

COLUMNS = 2
TILE_WIDTH = 200
TILE_HEIGHT = 56
SPACING = 8
MARGIN = 12
# Breedte zonder rand en schuifbalk; die komen er waar nodig bij (QuickPanel._fit).
WIDTH = COLUMNS * TILE_WIDTH + (COLUMNS - 1) * SPACING + 2 * MARGIN
GAP = 8
# Zoveel pixels slepen voordat een klik dimmen wordt.
DRAG_START = 6
# Pijltjestoetsen: pas na even stilstaan de helderheid versturen.
DIM_DELAY_MS = 400
# Zo lang de nieuwe helderheid tonen als HA geen andere meldt (bijv. omdat het mislukte).
DIM_HOLD_MS = 5000
# Klik op het tray-icoon zo kort nadat het paneel sloot: dat was dezelfde klik.
REOPEN_DELAY_S = 0.4


def can_position() -> bool:
    """Kan de app een popup bij het tray-icoon zetten?

    Niet op Wayland, ook niet via XWayland: daar kent de app de muispositie buiten
    zijn eigen vensters niet.
    """
    if QGuiApplication.platformName().startswith("wayland"):
        return False
    return not (sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY"))


@lru_cache(maxsize=1)
def panel_mode() -> str:
    if can_position():
        return "popup"
    return "kwin" if kwin.available() else "window"


def context_panel() -> bool:
    """Toont rechtsklik op het tray-icoon het paneel in plaats van een menu?

    Alleen waar dat zeker werkt: Windows (meldt de rechtsklik) en KDE Plasma (meldt dat
    een leeg menu open wil, zie app._setup_tray). Elders, en op Plasma 5 met Wayland,
    blijft een gewoon menu.
    """
    if sys.platform == "win32":
        return True
    return kwin.is_kde() and (can_position() or kwin.is_plasma6())


def panel_position(anchor: QRect, size: QSize, area: QRect) -> QPoint:
    """Linkerbovenhoek van het paneel: naast anchor (het tray-icoon), binnen area."""
    if anchor.center().y() > area.center().y():
        y = anchor.top() - size.height() - GAP  # taakbalk onderaan: erboven
    else:
        y = anchor.bottom() + GAP
    x = anchor.right() - size.width()
    x = max(area.left(), min(x, area.right() - size.width() + 1))
    y = max(area.top(), min(y, area.bottom() - size.height() + 1))
    return QPoint(x, y)


def _alpha(color: QColor, alpha: int) -> QColor:
    color = QColor(color)
    color.setAlpha(alpha)
    return color


class Tile(QWidget):
    """Eén entiteit als tegel; tekent zichzelf in de kleuren van het systeemthema."""

    def __init__(self, client: QuickClient, entry: dict) -> None:
        super().__init__()
        self.client, self.entry = client, entry
        self.entity_id = entry["entity_id"]
        self.setFixedHeight(TILE_HEIGHT)
        self.setMinimumWidth(TILE_WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self._press_x: float | None = None
        self._dragging = False
        self._dim: int | None = None  # helderheid tijdens slepen, tot HA de nieuwe meldt
        self._dim_sent_at: tuple | None = None  # status van deze lamp toen _dim verstuurd werd
        self._dim_timer = QTimer(self, singleShot=True, interval=DIM_DELAY_MS)
        self._dim_timer.timeout.connect(self._send_dim)
        self._dim_hold = QTimer(self, singleShot=True, interval=DIM_HOLD_MS)
        self._dim_hold.timeout.connect(self._drop_dim)

    @property
    def state(self) -> dict | None:
        return self.client.states.get(self.entity_id)

    @property
    def name(self) -> str:
        return self.entry.get("name") or entity_name(self.entity_id, self.state)

    def show_state(self, entry: dict) -> None:
        self.entry = entry
        if self._dim_sent_at is not None and self._light_state() != self._dim_sent_at:
            self._drop_dim()  # HA meldt de nieuwe helderheid
        self.setEnabled(self.client.state == "connected" and available(self.state))
        hint = _("Drag sideways to dim") if self._dimmable() else ""
        self.setToolTip(f"{self.name}\n{hint}".strip())
        self.update()

    def _dimmable(self) -> bool:
        return brightness_pct(self.entity_id, self.state) is not None

    # -- tekenen --------------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.5)
        pal = self.palette()
        text = pal.color(QPalette.ColorRole.ButtonText)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        shape = QPainterPath()
        shape.addRoundedRect(rect, 12, 12)
        p.fillPath(shape, pal.color(QPalette.ColorRole.Button))
        if self.underMouse() and self.isEnabled():
            p.fillPath(shape, _alpha(pal.color(QPalette.ColorRole.Highlight), 30))

        color = QColor(tile_color(self.entity_id, self.state) or text)
        active = bool(tile_color(self.entity_id, self.state))
        pct = self._dim if self._dim is not None else brightness_pct(self.entity_id, self.state)
        if pct:
            # Helderheid als balkje onderaan, zoals een schuifje.
            p.save()
            p.setClipPath(shape)
            p.fillRect(QRectF(rect.left(), rect.bottom() - 3, rect.width() * pct / 100, 3), color)
            p.restore()
        border = pal.color(QPalette.ColorRole.Highlight) if self.hasFocus() else _alpha(text, 30)
        p.setPen(border)
        p.drawPath(shape)

        circle = QRectF(10, (self.height() - 36) / 2, 36, 36)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_alpha(color, 50) if active else _alpha(text, 20))
        p.drawEllipse(circle)
        icon = entity_icon(self.entity_id, self.state, self.entry.get("icon", ""))
        icons.draw(p, circle.adjusted(7, 7, -7, -7), icon, color if active else _alpha(text, 180))

        left = circle.right() + 10
        width = rect.right() - left - 8
        font = self.font()
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(text)
        metrics = p.fontMetrics()
        p.drawText(QRectF(left, 9, width, metrics.height()), Qt.AlignmentFlag.AlignLeft,
                   metrics.elidedText(self.name, Qt.TextElideMode.ElideRight, int(width)))
        small = self.font()
        small.setPointSizeF(small.pointSizeF() * 0.9)
        p.setFont(small)
        p.setPen(_alpha(text, 160))
        if self._dim is None:
            status = state_text(self.entity_id, self.state)
        else:
            status = f"{_('On')} · {self._dim}%" if self._dim else _("Off")
        p.drawText(QRectF(left, self.height() - 9 - p.fontMetrics().height(), width, p.fontMetrics().height()),
                   Qt.AlignmentFlag.AlignLeft, status)

    # -- bediening ------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_x = event.position().x()
            self._dragging = False

    def mouseMoveEvent(self, event) -> None:
        if self._press_x is None or not self._dimmable():
            return
        x = event.position().x()
        if not self._dragging and abs(x - self._press_x) > DRAG_START:
            self._dragging = True
        if self._dragging:
            self._preview(round(x * 100 / max(1, self.width())))

    def mouseReleaseEvent(self, event) -> None:
        if self._press_x is None or event.button() != Qt.MouseButton.LeftButton:
            return
        dragging, self._press_x, self._dragging = self._dragging, None, False
        if dragging:
            self._send_dim()
        elif self.rect().contains(event.position().toPoint()):
            self.client.activate(self.entity_id)

    def mouseDoubleClickEvent(self, event) -> None:
        # Telt als één klik: de eerste klik schakelde al. (Standaard roept Qt hier
        # mousePressEvent aan, en dan ging de lamp aan en meteen weer uit.)
        event.accept()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not event.isAutoRepeat():
                self.client.activate(self.entity_id)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self._dimmable():
            current = self._dim if self._dim is not None else brightness_pct(self.entity_id, self.state) or 0
            self._preview(current + (10 if key == Qt.Key.Key_Right else -10))
            self._dim_timer.start()
        else:
            super().keyPressEvent(event)

    def _preview(self, pct: int) -> None:
        """Toon een nieuwe helderheid; een melding over een eerder verstuurde telt dan niet meer."""
        self._dim_hold.stop()
        self._dim_sent_at = None
        self._dim = max(0, min(100, pct))
        self.update()

    def _light_state(self) -> tuple:
        state = self.state or {}
        return state.get("state"), (state.get("attributes") or {}).get("brightness")

    def _send_dim(self) -> None:
        self._dim_timer.stop()
        if self._dim is not None:
            self._dim_sent_at = self._light_state()
            self._dim_hold.start()
            self.client.set_brightness(self.entity_id, self._dim)

    def _drop_dim(self) -> None:
        self._dim_hold.stop()
        self._dim = self._dim_sent_at = None
        self.update()


class _Heading(QWidget):
    def __init__(self, section: dict) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 6, 0, 0)
        color = _alpha(self.palette().color(QPalette.ColorRole.WindowText), 200)
        if icons.exists(section["icon"]):
            icon = QLabel()
            icon.setPixmap(icons.icon(section["icon"], color).pixmap(20, 20))
            row.addWidget(icon)
        label = QLabel(section["name"], textFormat=Qt.TextFormat.PlainText)
        font = label.font()
        font.setPointSizeF(font.pointSizeF() * 1.1)
        label.setFont(font)
        row.addWidget(label, 1)


class QuickPanel(QFrame):
    open_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self, client: QuickClient, mode: str | None = None) -> None:
        super().__init__()
        self.client = client
        self.mode = mode or panel_mode()
        if self.mode == "popup":
            self.setWindowFlags(Qt.WindowType.Popup)
        elif self.mode == "kwin":
            self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        if self.mode != "window":
            self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setWindowTitle(_("Quick controls — {app}").format(app=APP_NAME))
        self.setWindowIcon(app_icon())
        self._anchor = QRect()
        self._was_active = False
        self._hidden_at = 0.0

        title = QLabel(_("Quick controls"))
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        header = QHBoxLayout()
        header.addWidget(title, 1)
        color = self.palette().color(QPalette.ColorRole.WindowText)
        if self.mode == "kwin":
            close = QToolButton(autoRaise=True, toolTip=_("Close"), icon=icons.icon("mdi:close", color))
            close.clicked.connect(self.close)
            header.addWidget(close)

        self.message = _wrap("")
        self.content = QWidget()
        self.sections = QVBoxLayout(self.content)
        self.sections.setContentsMargins(0, 0, 0, 0)
        self.sections.setSpacing(SPACING)
        self.scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.content)

        # Wat anders in het menu van het tray-icoon staat.
        footer = QHBoxLayout()
        for icon, text, signal in [("mdi:open-in-app", _("Open"), self.open_requested),
                                   ("mdi:cog", _("Settings…"), self.settings_requested),
                                   ("mdi:power", _("Quit"), self.quit_requested)]:
            button = QToolButton(autoRaise=True, text=text, icon=icons.icon(icon, color))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.clicked.connect(lambda _checked=False, signal=signal: self._request(signal))
            if signal is self.quit_requested:
                footer.addStretch(1)
            footer.addWidget(button)

        col = QVBoxLayout(self)
        col.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        col.addLayout(header)
        col.addWidget(self.message)
        col.addWidget(self.scroll)
        col.addWidget(QFrame(frameShape=QFrame.Shape.HLine, frameShadow=QFrame.Shadow.Sunken))
        col.addLayout(footer)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.close)

        self.tiles: list[Tile] = []
        self._key: list[tuple] = []
        self._sections: list[QWidget] = []
        self._fit(scrolling=False)
        client.changed.connect(self._changed)
        client.status_changed.connect(self._changed)

    def toggle(self, anchor: QRect) -> None:
        """Klik op een tray-icoon: openen, of sluiten als het paneel open is."""
        if self.isVisible():
            self.close()
        elif time.monotonic() - self._hidden_at > REOPEN_DELAY_S:
            # Anders sloot deze klik het paneel net (focus kwijt), en moet het dicht blijven.
            self.popup(anchor)

    def popup(self, anchor: QRect) -> None:
        """Toon het paneel; anchor is de plek van het tray-icoon (of de muis)."""
        self._anchor = anchor
        self.refresh()
        if self.mode == "popup":
            self._place()
        elif self.mode == "kwin":
            kwin.place(self.windowTitle())
        self._was_active = False
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh(self) -> None:
        sections = self.client.sections()
        # Naam en icoon van de secties horen erbij: die staan in de koppen.
        key = [(section["name"], section["icon"], [e["entity_id"] for e in entries])
               for section, entries in sections]
        if key != self._key:
            self._rebuild(sections)
            self._key = key
        entries = [e for _section, group in sections for e in group]
        for entry, tile in zip(entries, self.tiles):
            tile.show_state(entry)

        state = self.client.state
        if not self.client.entity_ids:
            text = _("Choose in Settings which lights, switches and scenes appear here.")
        elif state == "connected":
            text = "" if self.tiles else _("The chosen devices weren't found in Home Assistant.")
        elif state == "connecting":
            text = _("Connecting…")
        else:
            text = self.client.detail or _("Not connected.")
        self.message.setText(text)
        self.message.setVisible(bool(text))
        self.scroll.setVisible(bool(self.tiles))
        screen = self.screen() or QGuiApplication.primaryScreen()
        max_height = int(screen.availableGeometry().height() * 0.7)
        content = self.content.sizeHint().height()
        self._fit(scrolling=content > max_height)
        self.scroll.setFixedHeight(min(content, max_height))
        self.adjustSize()
        if self.mode == "popup" and self.isVisible():
            self._place()  # gegroeid: weer tegen de taakbalk (in kwin-modus doet KWin dat)

    def _fit(self, scrolling: bool) -> None:
        """Twee tegels naast elkaar, plus de rand en zo nodig de schuifbalk."""
        bar = self.scroll.verticalScrollBar().sizeHint().width() if scrolling else 0
        self.setFixedWidth(WIDTH + 2 * self.frameWidth() + bar)

    def _place(self) -> None:
        screen = QGuiApplication.screenAt(self._anchor.center()) or QGuiApplication.primaryScreen()
        self.move(panel_position(self._anchor, self.size(), screen.availableGeometry()))

    def _rebuild(self, sections: list[tuple[dict, list[dict]]]) -> None:
        for widget in self._sections:
            self.sections.removeWidget(widget)
            widget.deleteLater()
        self._sections, self.tiles = [], []
        for section, entries in sections:
            box = QWidget()
            col = QVBoxLayout(box)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(SPACING)
            if section["name"] or section["icon"]:
                col.addWidget(_Heading(section))
            grid = QGridLayout()
            grid.setSpacing(SPACING)
            for n, entry in enumerate(entries):
                tile = Tile(self.client, entry)
                grid.addWidget(tile, n // COLUMNS, n % COLUMNS)
                self.tiles.append(tile)
            for column in range(COLUMNS):
                grid.setColumnStretch(column, 1)
            col.addLayout(grid)
            self.sections.addWidget(box)
            self._sections.append(box)

    def _changed(self, *args) -> None:
        if self.isVisible():
            self.refresh()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._hidden_at = time.monotonic()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.mode == "kwin":
            # Net als een popup: dicht zodra je ergens anders klikt.
            if self.isActiveWindow():
                self._was_active = True
            elif self._was_active and self.isVisible():
                self.hide()

    def _request(self, signal) -> None:
        self.close()
        signal.emit()
