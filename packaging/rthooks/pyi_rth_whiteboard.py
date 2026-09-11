"""Mark the frozen process as a packaged Flet/Playwright app before imports run."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _bundle_dir() -> Path | None:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


os.environ.setdefault("FLET_APP_PACKAGED", "1")
# Playwright looks inside its own package for browsers when this is "0".
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

_bundle = _bundle_dir()
if _bundle is not None:
    client_dir = _bundle / "flet_desktop" / "app"
    if client_dir.is_dir():
        try:
            import flet_desktop

            flet_desktop.get_package_bin_dir = lambda: str(client_dir)
        except Exception:
            pass


def _crash_log_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "WhiteBoard" / "crash.log"
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return base / "WhiteBoard" / "crash.log"
    return Path.home() / ".whiteboard" / "crash.log"


def _handle_exception(exc_type, exc, tb) -> None:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    log_path = _crash_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(text, encoding="utf-8")
    except Exception:
        log_path = Path.home() / "WhiteBoard-crash.log"
        try:
            log_path.write_text(text, encoding="utf-8")
        except Exception:
            pass
    if sys.platform == "darwin":
        try:
            import subprocess

            subprocess.run(
                [
                    "/usr/bin/osascript",
                    "-e",
                    f'display dialog "WhiteBoard could not start. A crash log was saved to {log_path}." '
                    'buttons {"OK"} default button "OK" with icon stop',
                ],
                check=False,
                capture_output=True,
            )
        except Exception:
            pass
    sys.__excepthook__(exc_type, exc, tb)


sys.excepthook = _handle_exception
