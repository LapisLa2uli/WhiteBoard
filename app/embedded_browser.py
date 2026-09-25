"""Edge or Chrome window hosted inside the WhiteBoard window.

The signed-in Playwright session stays in the background. This window is a
separate app-mode browser that receives those cookies, so Blackboard pages
open without asking for a second login.
"""

from __future__ import annotations

import ctypes
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Callable

TOOLBAR_HEIGHT = 56

_EDGE_CANDIDATES = (
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "Microsoft"
    / "Edge"
    / "Application"
    / "msedge.exe",
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    / "Microsoft"
    / "Edge"
    / "Application"
    / "msedge.exe",
)
_CHROME_CANDIDATES = (
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    / "Google"
    / "Chrome"
    / "Application"
    / "chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "Google"
    / "Chrome"
    / "Application"
    / "chrome.exe",
)


def browser_executable() -> Path | None:
    for path in (*_EDGE_CANDIDATES, *_CHROME_CANDIDATES):
        if path.is_file():
            return path
    return None


def cookies_from_storage(state: dict | None) -> list[dict]:
    """Playwright storage cookies, shaped for context.add_cookies."""
    if not isinstance(state, dict):
        return []
    cleaned: list[dict] = []
    for cookie in state.get("cookies") or []:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name") or "")
        domain = str(cookie.get("domain") or "")
        if not name or cookie.get("value") is None or not domain:
            continue
        item: dict = {
            "name": name,
            "value": str(cookie.get("value")),
            "domain": domain,
            "path": str(cookie.get("path") or "/"),
        }
        if cookie.get("httpOnly"):
            item["httpOnly"] = True
        if cookie.get("secure"):
            item["secure"] = True
        same = str(cookie.get("sameSite") or "Lax")
        item["sameSite"] = same if same in {"Strict", "Lax", "None"} else "Lax"
        expires = cookie.get("expires")
        if isinstance(expires, (int, float)) and expires > 0:
            item["expires"] = float(expires)
        cleaned.append(item)
    return cleaned


class EmbeddedBrowser:
    def __init__(
        self,
        *,
        on_url: Callable[[str], None],
        on_fail: Callable[[str], None],
        on_closed: Callable[[], None],
        owner_hwnd: Callable[[], int],
    ) -> None:
        self._on_url = on_url
        self._on_fail = on_fail
        self._on_closed = on_closed
        self._owner_hwnd = owner_hwnd
        self._commands: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = False
        self._proc: subprocess.Popen | None = None
        self._profile: Path | None = None
        self._storage: dict | None = None

    def show(self, url: str, storage_state: dict | None = None) -> None:
        with self._lock:
            self._storage = storage_state
            self._stop = False
            alive = self._thread is not None and self._thread.is_alive()
        if alive:
            self._commands.put(("goto", url))
            return
        thread = threading.Thread(
            target=self._run, args=(url,), name="bb-viewer", daemon=True
        )
        with self._lock:
            self._thread = thread
        thread.start()

    def command(self, name: str, payload: str | None = None) -> None:
        self._commands.put((name, payload))

    def close(self) -> None:
        with self._lock:
            self._stop = True
        self._commands.put(("close", None))
        self._kill_process()

    def _run(self, url: str) -> None:
        opened = False
        try:
            self._open(url)
            opened = True
        except Exception as exc:
            if not self._stop:
                self._on_fail(str(exc).strip() or "Couldn't open the page.")
        finally:
            self._kill_process()
            profile = self._profile
            self._profile = None
            if profile is not None:
                shutil.rmtree(profile, ignore_errors=True)
            if opened and not self._stop:
                self._on_closed()

    def _open(self, url: str) -> None:
        executable = browser_executable()
        if executable is None:
            raise RuntimeError("Install Edge or Chrome to open pages inside WhiteBoard.")
        profile = Path(tempfile.mkdtemp(prefix="whiteboard-viewer-"))
        self._profile = profile
        self._proc = subprocess.Popen(
            [
                str(executable),
                f"--app={url}",
                "--remote-debugging-port=0",
                f"--user-data-dir={profile}",
                "--window-position=-32000,-32000",
                "--window-size=1100,720",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--disable-sync",
                "--disable-features=Translate,TranslateUI",
            ]
        )
        port = _wait_for_port(profile)
        if self._stop:
            return
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()
            with self._lock:
                storage = self._storage
            cookies = cookies_from_storage(storage)
            if cookies:
                try:
                    context.add_cookies(cookies)
                except Exception:
                    for cookie in cookies:
                        try:
                            context.add_cookies([cookie])
                        except Exception:
                            continue
            hwnd = _wait_for_hwnd(self._proc.pid)
            if not hwnd:
                raise RuntimeError("Couldn't place the page in the window.")
            _own_window(hwnd, self._owner_hwnd())
            self._place(hwnd)
            if self._stop:
                return
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            except Exception:
                pass
            self._on_url(page.url or url)
            self._loop(page, hwnd)

    def _loop(self, page, hwnd: int) -> None:
        last_url = ""
        while not self._stop:
            if self._proc is not None and self._proc.poll() is not None:
                return
            try:
                command = self._commands.get(timeout=0.15)
            except queue.Empty:
                command = None
            if command:
                name, payload = command
                if name == "close":
                    self._stop = True
                    return
                try:
                    if name == "goto" and payload:
                        page.goto(payload, wait_until="domcontentloaded", timeout=45_000)
                    elif name == "back":
                        page.go_back(wait_until="domcontentloaded", timeout=20_000)
                    elif name == "forward":
                        page.go_forward(wait_until="domcontentloaded", timeout=20_000)
                    elif name == "reload":
                        page.reload(wait_until="domcontentloaded", timeout=45_000)
                except Exception:
                    pass
            if not hwnd or not _is_window(hwnd):
                if self._proc is not None:
                    hwnd = _find_hwnd(self._proc.pid)
            if hwnd:
                self._place(hwnd)
            try:
                current = page.url or ""
            except Exception:
                return
            if current and current != last_url:
                last_url = current
                self._on_url(current)

    def _place(self, hwnd: int) -> None:
        owner = self._owner_hwnd()
        if not owner or not _is_window(owner) or not _is_window(hwnd):
            return
        _own_window(hwnd, owner)
        if _is_minimized(owner):
            _show(hwnd, False)
            return
        bounds = _content_bounds(owner, TOOLBAR_HEIGHT)
        if bounds is None:
            return
        x, y, width, height = bounds
        if width < 80 or height < 80:
            return
        _move(hwnd, x, y, width, height)
        _show(hwnd, True)

    def _kill_process(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None or proc.poll() is not None:
            return
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=8,
            )
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _wait_for_port(profile: Path) -> str:
    port_file = profile / "DevToolsActivePort"
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if port_file.exists():
            line = port_file.read_text(encoding="utf-8", errors="replace").splitlines()
            if line and line[0].strip().isdigit():
                return line[0].strip()
        time.sleep(0.1)
    raise RuntimeError("The page viewer didn't start.")


def _wait_for_hwnd(pid: int) -> int:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        hwnd = _find_hwnd(pid)
        if hwnd:
            return hwnd
        time.sleep(0.1)
    return 0


def _find_hwnd(pid: int) -> int:
    if not pid:
        return 0
    pids = _family_pids(pid)
    found: list[tuple[int, int]] = []

    def visit(hwnd, _extra) -> None:
        if not _is_window(hwnd) or not _is_visible(hwnd):
            return
        if _window_pid(hwnd) not in pids:
            return
        if _class_name(hwnd) != "Chrome_WidgetWin_1":
            return
        rect = _window_rect(hwnd)
        if rect is None:
            return
        area = max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])
        if area < 200 * 200 and rect[0] > -16000:
            return
        found.append((area, hwnd))

    _enum_windows(visit)
    if not found:
        return 0
    found.sort()
    return found[-1][1]


def _family_pids(root: int) -> set[int]:
    pids = {root}
    try:
        children = _child_pids()
    except Exception:
        return pids
    changed = True
    while changed:
        changed = False
        for pid, parent in children.items():
            if parent in pids and pid not in pids:
                pids.add(pid)
                changed = True
    return pids


def _child_pids() -> dict[int, int]:
    snapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot in (-1, 0xFFFFFFFF):
        raise OSError("process snapshot failed")
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        pairs: dict[int, int] = {}
        ok = ctypes.windll.kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            pairs[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            ok = ctypes.windll.kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        return pairs
    finally:
        ctypes.windll.kernel32.CloseHandle(snapshot)


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def _content_bounds(owner: int, toolbar: int) -> tuple[int, int, int, int] | None:
    try:
        import win32gui
    except Exception:
        return None
    left, top, right, bottom = win32gui.GetClientRect(owner)
    origin = win32gui.ClientToScreen(owner, (0, 0))
    dpi = 96
    try:
        dpi = int(ctypes.windll.user32.GetDpiForWindow(owner) or 96)
    except Exception:
        dpi = 96
    bar = int(round(toolbar * dpi / 96))
    return origin[0], origin[1] + bar, right - left, bottom - top - bar


def _own_window(hwnd: int, owner: int) -> None:
    if not owner:
        return
    try:
        import win32con
        import win32gui

        win32gui.SetWindowLong(hwnd, win32con.GWL_HWNDPARENT, owner)
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        style = (style | win32con.WS_EX_TOOLWINDOW) & ~win32con.WS_EX_APPWINDOW
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style)
    except Exception:
        return


def _move(hwnd: int, x: int, y: int, width: int, height: int) -> None:
    try:
        import win32con
        import win32gui

        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOP,
            int(x),
            int(y),
            int(width),
            int(height),
            win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW,
        )
    except Exception:
        return


def _show(hwnd: int, visible: bool) -> None:
    try:
        import win32con
        import win32gui

        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNA if visible else win32con.SW_HIDE)
    except Exception:
        return


def _is_minimized(hwnd: int) -> bool:
    try:
        import win32gui

        return bool(win32gui.IsIconic(hwnd))
    except Exception:
        return False


def _is_window(hwnd: int) -> bool:
    try:
        import win32gui

        return bool(hwnd and win32gui.IsWindow(hwnd))
    except Exception:
        return False


def _is_visible(hwnd: int) -> bool:
    try:
        import win32gui

        return bool(win32gui.IsWindowVisible(hwnd))
    except Exception:
        return False


def _window_pid(hwnd: int) -> int:
    try:
        import win32process

        _thread, pid = win32process.GetWindowThreadProcessId(hwnd)
        return int(pid)
    except Exception:
        return 0


def _class_name(hwnd: int) -> str:
    try:
        import win32gui

        return str(win32gui.GetClassName(hwnd))
    except Exception:
        return ""


def _window_rect(hwnd: int):
    try:
        import win32gui

        return win32gui.GetWindowRect(hwnd)
    except Exception:
        return None


def _enum_windows(callback) -> None:
    try:
        import win32gui

        win32gui.EnumWindows(callback, None)
    except Exception:
        return
