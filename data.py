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

DATA_DIR = Path.home() / ".whiteboard_slim"
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
