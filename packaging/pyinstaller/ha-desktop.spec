# PyInstaller-recept voor Windows, macOS en Linux (AppImage/.deb).
# Bouwen: python packaging/pyinstaller/make_icons.py && pyinstaller packaging/pyinstaller/ha-desktop.spec
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ha_desktop  # noqa: E402

ICON = str(ROOT / "build" / ("icon.ico" if sys.platform == "win32" else "icon.png"))

a = Analysis(
    [str(ROOT / "packaging/pyinstaller/entry.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "ha_desktop/data"), "ha_desktop/data")],
    hiddenimports=collect_submodules("ha_desktop") + collect_submodules("keyring.backends"),
    excludes=["gi", "tkinter"],
)

# PyInstaller neemt via QtWebEngine bijna heel Qt mee; gooi weg wat de app niet gebruikt.
_UNUSED = re.compile(
    r"Qt6?(3D|Charts|DataVisualization|Graphs|Location|Multimedia|Labs|QuickControls2|QuickDialogs2"
    r"|QuickTimeline|QuickParticles|QuickShapes|QuickEffects|QuickVectorImage|Quick3D|Sensors|Serial"
    r"|Bluetooth|Nfc|RemoteObjects|Scxml|StateMachine|TextToSpeech|VirtualKeyboard|SpatialAudio"
    r"|Designer|Help|UiTools|HttpServer|Protobuf|Grpc|ShaderTools|WebView|WebSockets?Qml)"
)
_KEEP_LOCALES = ("en-US.pak", "nl.pak")


def _wanted(dest: str) -> bool:
    path = dest.replace("\\", "/")
    name = path.rsplit("/", 1)[-1]
    if "/Qt/qml/" in path or "/qml/" in path:
        return False
    if "qtwebengine_locales/" in path:
        return name in _KEEP_LOCALES
    if "/translations/" in path and name.endswith(".qm"):
        return name.startswith(("qtbase_", "qt_", "qtwebengine_"))
    if "qgtk3" in name or name.startswith(("libgtk-3", "libgdk-3", "libglycin")):
        return False  # GTK-thema-plugin; zou een eigen GTK meebundelen
    return not _UNUSED.search(path)


a.binaries = [b for b in a.binaries if _wanted(b[0])]
a.datas = [d for d in a.datas if _wanted(d[0])]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ha-desktop",
    console=False,
    icon=ICON,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ha-desktop")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Home Assistant Desktop.app",
        icon=ICON,
        bundle_identifier=ha_desktop.APP_ID,
        version=ha_desktop.__version__,
        info_plist={
            "CFBundleDisplayName": "Home Assistant Desktop",
            "CFBundleShortVersionString": ha_desktop.__version__,
            "NSHighResolutionCapable": True,
            "NSMicrophoneUsageDescription": "Used for voice commands (Assist) in Home Assistant.",
        },
    )
