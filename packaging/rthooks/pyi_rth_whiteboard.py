"""Mark the frozen process as a packaged Flet/Playwright app before imports run."""

from __future__ import annotations

import os
import shutil
import sys
import tarfile
import traceback
from pathlib import Path


def _bundle_dir() -> Path | None:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    if not getattr(sys, "frozen", False):
        return None
    exe_dir = Path(sys.executable).resolve().parent
    for candidate in (
        exe_dir,
        exe_dir / "_internal",
        exe_dir.parent / "Resources" / "_internal",
        exe_dir.parent / "Frameworks" / "_internal",
        exe_dir.parent / "Frameworks",
        exe_dir.parent / "Resources",
    ):
        if (candidate / "playwright").is_dir() or (candidate / "flet_desktop").is_dir():
            return candidate
    return exe_dir


def _extract_playwright_browsers(bundle: Path) -> None:
    archive = bundle / "playwright" / "driver" / "package" / "playwright-chromium.tar.gz"
    if not archive.is_file():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
        return
    if sys.platform == "darwin":
        dest = Path.home() / "Library" / "Application Support" / "WhiteBoard" / "ms-playwright"
    else:
        dest = Path.home() / "AppData" / "Local" / "WhiteBoard" / "ms-playwright"
    ready = dest / ".ready"
    if not ready.is_file():
        staging = dest.with_name(dest.name + ".tmp")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(staging)
        (staging / ".ready").write_text("ok", encoding="utf-8")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        staging.replace(dest)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(dest)


os.environ.setdefault("FLET_APP_PACKAGED", "1")

_bundle = _bundle_dir()
if _bundle is not None:
    _extract_playwright_browsers(_bundle)
    client_dir = _bundle / "flet_desktop" / "app"
    if client_dir.is_dir():
        try:
            import flet_desktop

            flet_desktop.get_package_bin_dir = lambda: str(client_dir)
        except Exception:
            pass
else:
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")


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
