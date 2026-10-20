from pathlib import Path

from PySide6.QtGui import QIcon

from ha_desktop import APP_ID

_DATA = Path(__file__).resolve().parent / "data"


def icon_path() -> Path:
    return _DATA / f"{APP_ID}.svg"


def app_icon() -> QIcon:
    return QIcon.fromTheme(APP_ID, QIcon(str(icon_path())))
