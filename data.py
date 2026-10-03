"""WhiteBoard keeps its data in the home folder. It does not read the archived app's files."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_root() -> Path:
    """Folder that holds static/ and assets/, including inside a packaged app."""
    if getattr(sys, "frozen", False):
        bundled = getattr(sys, "_MEIPASS", None)
        if bundled:
            return Path(bundled)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = resource_root()
if not getattr(sys, "frozen", False) and str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def data_dir() -> Path:
    """Where the app keeps its snapshot, settings, and saved session.

    Windows stays on the folder it has always used, so an upgrade does not
    quietly empty a returning user's dashboard. macOS gets its own hidden
    folder, and nothing WebKit needs lives outside it: host/_macos.py keeps its
    own cookie jar rather than letting WebKit scatter one into ~/Library.
    """
    if sys.platform == "darwin":
        return Path.home() / ".config" / "whiteboard"
    return Path.home() / ".whiteboard_slim"


DATA_DIR = data_dir()
SNAPSHOT_PATH = DATA_DIR / "snapshot.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
GOOGLE_PATH = DATA_DIR / "google_calendar.json"
WEBVIEW_PATH = DATA_DIR / "webview"

_installed = False


def install() -> None:
    """Point shared modules at this app's data folder for this process only."""
    global _installed
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    import blackboard.store as store

    store.DATA_DIR = DATA_DIR
    store.SNAPSHOT_PATH = SNAPSHOT_PATH
    store.SETTINGS_PATH = SETTINGS_PATH
    import app.google_calendar as google

    google.DATA_DIR = DATA_DIR
    google.ACCOUNT_PATH = GOOGLE_PATH
    _installed = True
