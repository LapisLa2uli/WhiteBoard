"""Slim WhiteBoard keeps its own data. It does not read the original app's files."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR = Path.home() / ".whiteboard_slim"
SNAPSHOT_PATH = DATA_DIR / "snapshot.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
GOOGLE_PATH = DATA_DIR / "google_calendar.json"
WEBVIEW_PATH = DATA_DIR / "webview"

_installed = False


def install() -> None:
    """Point shared modules at the slim data folder for this process only."""
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
