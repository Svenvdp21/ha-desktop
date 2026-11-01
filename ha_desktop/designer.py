"""Editor voor de indeling van de snelbediening: secties met tegels, zoals een HA-dashboard.

Links alle apparaten (aanvinken = tegel toevoegen), rechts de indeling: slepen om
te ordenen, dubbelklikken om een naam of icoon (mdi:…) te wijzigen.
"""

from __future__ import annotations

import shiboken6
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QFont, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ha_desktop import APP_NAME, icons
from ha_desktop.config import Config
from ha_desktop.haapi import Result
from ha_desktop.i18n import _
from ha_desktop.onboarding import _wrap
from ha_desktop.quick import DOMAINS, clean_layout, domain, entity_icon, entity_name, layout_by_area, sort_key

# Gegevens per boomitem (kolom 0): soort, entity_id en eigen naam ("" = naam uit HA).
KIND = Qt.ItemDataRole.UserRole
ENTITY = Qt.ItemDataRole.UserRole + 1
NAME = Qt.ItemDataRole.UserRole + 2
SECTION, TILE = "section", "tile"

REGISTRY_REQUESTS = [
    {"type": "config/area_registry/list"},
    {"type": "config/device_registry/list"},
    {"type": "config/entity_registry/list_for_display"},
]


def _is_section(item: QTreeWidgetItem) -> bool:
    return item.data(0, KIND) == SECTION


class LayoutTree(QTreeWidget):
    """Boom met secties en tegels; houdt na slepen de structuur geldig."""

    structure_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setColumnCount(2)
        self.setHeaderLabels([_("Name"), _("Icon (mdi:…)")])
        self.setColumnWidth(0, 260)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                             | QAbstractItemView.EditTrigger.EditKeyPressed)

    def dropEvent(self, event) -> None:
        super().dropEvent(event)
        self.normalize()
        self.structure_changed.emit()

    def normalize(self) -> None:
        """Secties alleen bovenaan, tegels alleen in een sectie."""
        root = self.invisibleRootItem()
        i = 0
        while i < root.childCount():
            item = root.child(i)
            if not _is_section(item):
                root.takeChild(i)
                if i > 0:
                    root.child(i - 1).addChild(item)
                elif root.childCount() and _is_section(root.child(0)):
                    root.child(0).insertChild(0, item)  # boven de eerste sectie gesleept
                else:
                    section = new_section("")
                    section.addChild(item)
                    root.insertChild(0, section)
                continue
            j, after = 0, i + 1
            while j < item.childCount():
                if _is_section(item.child(j)):
                    root.insertChild(after, item.takeChild(j))  # sectie in een sectie gesleept
                    after += 1
                else:
                    j += 1
            i += 1
        self.expandAll()


def new_section(name: str, icon: str = "") -> QTreeWidgetItem:
    item = QTreeWidgetItem()
    item.setData(0, KIND, SECTION)
    item.setData(0, NAME, name)
    item.setText(1, icon)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
                  | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
    return item


def new_tile(entry: dict) -> QTreeWidgetItem:
    item = QTreeWidgetItem()
    item.setData(0, KIND, TILE)
    item.setData(0, ENTITY, entry["entity_id"])
    item.setData(0, NAME, entry.get("name", ""))
    item.setText(1, entry.get("icon", ""))
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
                  | Qt.ItemFlag.ItemIsDragEnabled)
    return item


class LayoutEditor(QDialog):
    def __init__(self, config: Config, api, tokens, layout: list[dict], parent=None) -> None:
        super().__init__(parent)
        # Niet dezelfde titel als het paneel: daaraan herkent het KWin-script dat.
        self.setWindowTitle(_("Design quick controls — {app}").format(app=APP_NAME))
        self.resize(900, 580)
        self.config, self.api, self.tokens = config, api, tokens
        self.states: dict[str, dict] = {}
        self._token = ""
        self.token_saved = False  # nieuw token in de sleutelbos gezet

        # Links: apparaten
        devices = QGroupBox(_("Devices"))
        left = QVBoxLayout(devices)
        self.status = _wrap("")
        self.token = QLineEdit(placeholderText=_("Paste your token here"))
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.returnPressed.connect(self.load)
        load = QPushButton(_("Load devices"))
        load.clicked.connect(self.load)
        self.token_row = QWidget()
        row = QHBoxLayout(self.token_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.token, 1)
        row.addWidget(load)
        self.search = QLineEdit(placeholderText=_("Search…"))
        self.search.textChanged.connect(self._filter)
        self.list = QListWidget()
        self.list.itemChanged.connect(self._checked)
        for w in (self.status, self.token_row, self.search):
            left.addWidget(w)
        left.addWidget(self.list, 1)

        # Rechts: indeling
        design = QGroupBox(_("Layout"))
        right = QVBoxLayout(design)
        right.addWidget(_wrap(_("Drag to reorder. Double-click a name or icon to change it; icons are "
                                "Material Design Icons like <code>mdi:sofa</code>, as in Home Assistant.")))
        self.tree = LayoutTree()
        self.tree.itemChanged.connect(self._edited)
        self.tree.structure_changed.connect(self._sync_checks)
        self.tree.structure_changed.connect(self._decorate_all)
        right.addWidget(self.tree, 1)
        tools = QHBoxLayout()
        add = QPushButton(_("Add section"))
        add.clicked.connect(self._add_section)
        up = QPushButton(_("Up"))
        up.clicked.connect(lambda: self._move(-1))
        down = QPushButton(_("Down"))
        down.clicked.connect(lambda: self._move(1))
        remove = QPushButton(_("Remove"))
        remove.clicked.connect(self._remove)
        QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), self.tree, activated=self._remove,
                  context=Qt.ShortcutContext.WidgetShortcut)
        self.by_area = QPushButton(_("Arrange by area"))
        self.by_area.setToolTip(_("One section per area in Home Assistant, with all lights, switches "
                                  "and scenes in it."))
        self.by_area.clicked.connect(self._arrange_by_area)
        self.by_area.setEnabled(False)
        for button in (add, up, down, remove):
            tools.addWidget(button)
        tools.addStretch(1)
        tools.addWidget(self.by_area)
        right.addLayout(tools)

        panes = QHBoxLayout()
        panes.addWidget(devices, 2)
        panes.addWidget(design, 3)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(_("OK"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(_("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        col = QVBoxLayout(self)
        col.addLayout(panes, 1)
        col.addWidget(buttons)

        self._fill_tree(clean_layout(layout))
        self.search.hide()
        if tokens.get(config.server_url):
            self.token_row.hide()
            self.load()
        else:
            self._message(_("Quick controls use the same access token as notifications; see "
                            "<i>Notifications</i> in Settings for how to create one. Paste it here:"))

    # -- resultaat ------------------------------------------------------------

    def layout(self) -> list[dict]:
        sections = []
        for i in range(self.tree.topLevelItemCount()):
            section = self.tree.topLevelItem(i)
            entities = []
            for j in range(section.childCount()):
                item = section.child(j)
                entry = {"entity_id": item.data(0, ENTITY)}
                if item.data(0, NAME):
                    entry["name"] = item.data(0, NAME)
                if item.text(1):
                    entry["icon"] = item.text(1)
                entities.append(entry)
            sections.append({"name": section.data(0, NAME), "icon": section.text(1), "entities": entities})
        return sections

    # -- apparaten laden ------------------------------------------------------

    def load(self) -> None:
        token = self.token.text().strip() or self.tokens.get(self.config.server_url)
        if not token:
            self._message(_("Enter a token first."), error=True)
            return
        self.token_row.setEnabled(False)
        self._message(_("Loading devices…"))
        self.api.get_states(self.config.server_url, token, lambda r: self._loaded(r, token))

    def _loaded(self, result: Result, token: str) -> None:
        if not shiboken6.isValid(self):
            return  # venster is intussen gesloten
        self.token_row.setEnabled(True)
        if not result.ok:
            self._message(result.error, error=True)
            self.token_row.show()
            return
        if token != self.tokens.get(self.config.server_url):
            self.tokens.set(self.config.server_url, token)
            self.token_saved = True
        self._token = token
        self.token.clear()
        self.token_row.hide()
        states = sorted((s for s in result.data["states"]
                         if isinstance(s, dict) and domain(str(s.get("entity_id", ""))) in DOMAINS), key=sort_key)
        self.states = {s["entity_id"]: s for s in states}
        self.list.blockSignals(True)
        self.list.clear()
        for state in states:
            item = QListWidgetItem(entity_name(state["entity_id"], state))
            item.setToolTip(state["entity_id"])
            item.setData(Qt.ItemDataRole.UserRole, state["entity_id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setIcon(icons.icon(entity_icon(state["entity_id"], state), self._text_color()))
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._sync_checks()
        self._decorate_all()
        self.by_area.setEnabled(True)
        self.search.show()
        self._filter(self.search.text())
        if states:
            self._message(_("Tick a device to add it to the selected section."))
        else:
            self._message(_("No lights, switches or scenes found in Home Assistant."))

    # -- boom -----------------------------------------------------------------

    def _fill_tree(self, layout: list[dict]) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        for section in layout:
            item = new_section(section["name"], section["icon"])
            for entry in section["entities"]:
                item.addChild(new_tile(entry))
            self.tree.addTopLevelItem(item)
        self.tree.expandAll()
        self.tree.blockSignals(False)
        self._decorate_all()

    def _decorate_all(self) -> None:
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            section = self.tree.topLevelItem(i)
            self._decorate(section)
            for j in range(section.childCount()):
                self._decorate(section.child(j))
        self.tree.blockSignals(False)

    def _decorate(self, item: QTreeWidgetItem) -> None:
        """Toon naam en icoon; eigen naam en icoon staan in NAME en kolom 1."""
        color = self._text_color()
        font = QFont(self.tree.font())
        if _is_section(item):
            name = item.data(0, NAME)
            font.setBold(True)
            font.setItalic(not name)
            item.setText(0, name or _("(no heading)"))
            item.setIcon(0, icons.icon(item.text(1), color))
            item.setToolTip(0, "")
        else:
            entity_id = item.data(0, ENTITY)
            state = self.states.get(entity_id)
            item.setText(0, item.data(0, NAME) or entity_name(entity_id, state))
            item.setIcon(0, icons.icon(entity_icon(entity_id, state, item.text(1)), color))
            item.setToolTip(0, entity_id)
        item.setFont(0, font)
        unknown = bool(item.text(1)) and not icons.exists(item.text(1))
        if unknown:
            item.setForeground(1, QBrush(Qt.GlobalColor.red))
        else:
            item.setData(1, Qt.ItemDataRole.ForegroundRole, None)
        item.setToolTip(1, _("Unknown icon") if unknown else "")

    def _edited(self, item: QTreeWidgetItem, column: int) -> None:
        self.tree.blockSignals(True)
        try:
            text = item.text(column).strip()
            if column == 1:
                item.setText(1, icons.normalize(text))
            elif _is_section(item):
                item.setData(0, NAME, "" if text == _("(no heading)") else text)
            else:
                entity_id = item.data(0, ENTITY)
                # Leeg of gelijk aan de naam in HA: geen eigen naam.
                same = text == entity_name(entity_id, self.states.get(entity_id))
                item.setData(0, NAME, "" if same else text)
            self._decorate(item)
        finally:
            self.tree.blockSignals(False)

    def _target_section(self) -> QTreeWidgetItem:
        item = self.tree.currentItem()
        if item is not None:
            return item if _is_section(item) else item.parent()
        if self.tree.topLevelItemCount():
            return self.tree.topLevelItem(self.tree.topLevelItemCount() - 1)
        section = new_section("")
        self.tree.addTopLevelItem(section)
        self._decorate(section)
        return section

    def _add_section(self) -> None:
        self.tree.blockSignals(True)
        section = new_section(_("New section"))
        self.tree.addTopLevelItem(section)
        self._decorate(section)
        self.tree.blockSignals(False)
        self.tree.setCurrentItem(section)
        self.tree.editItem(section, 0)

    def _move(self, step: int) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        parent = item.parent() or self.tree.invisibleRootItem()
        index = parent.indexOfChild(item) + step
        if not 0 <= index < parent.childCount():
            return
        parent.takeChild(index - step)
        parent.insertChild(index, item)
        self.tree.expandAll()
        self.tree.setCurrentItem(item)

    def _remove(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        (item.parent() or self.tree.invisibleRootItem()).removeChild(item)
        self._sync_checks()

    # -- apparatenlijst -------------------------------------------------------

    def _tree_entities(self) -> set[str]:
        return {self.tree.topLevelItem(i).child(j).data(0, ENTITY)
                for i in range(self.tree.topLevelItemCount())
                for j in range(self.tree.topLevelItem(i).childCount())}

    def _sync_checks(self) -> None:
        present = self._tree_entities()
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            item = self.list.item(i)
            checked = item.data(Qt.ItemDataRole.UserRole) in present
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.list.blockSignals(False)

    def _checked(self, item: QListWidgetItem) -> None:
        entity_id = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self.tree.blockSignals(True)
            tile = new_tile({"entity_id": entity_id})
            section = self._target_section()
            section.addChild(tile)
            section.setExpanded(True)
            self._decorate(tile)
            self.tree.blockSignals(False)
        else:
            for i in range(self.tree.topLevelItemCount()):
                section = self.tree.topLevelItem(i)
                for j in reversed(range(section.childCount())):
                    if section.child(j).data(0, ENTITY) == entity_id:
                        section.removeChild(section.child(j))

    def _filter(self, text: str) -> None:
        text = text.strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(text not in f"{item.text()} {item.toolTip()}".lower())

    # -- per ruimte -----------------------------------------------------------

    def _arrange_by_area(self) -> None:
        if self.tree.topLevelItemCount():
            answer = QMessageBox.question(self, _("Arrange by area"),
                                          _("Replace your current layout with one section per area?"))
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.by_area.setEnabled(False)
        self._message(_("Loading areas…"))
        self.api.ws_request(self.config.server_url, self._token, REGISTRY_REQUESTS, self._areas_loaded)

    def _areas_loaded(self, result: Result) -> None:
        if not shiboken6.isValid(self):
            return
        self.by_area.setEnabled(True)
        if not result.ok:
            self._message(result.error, error=True)
            return
        areas, devices, display = result.data["results"]
        layout = layout_by_area(list(self.states.values()), areas or [], devices or [],
                                (display or {}).get("entities", []))
        self._fill_tree(layout)
        self._sync_checks()
        self._message(_("Arranged by area. Remove what you don't need, or drag tiles around."))

    # -- hulpjes --------------------------------------------------------------

    def _text_color(self):
        return self.palette().color(QPalette.ColorRole.Text)

    def _message(self, text: str, error: bool = False) -> None:
        self.status.setText(f"<span style='color:#d33'>{text}</span>" if error else text)
        self.status.show()
