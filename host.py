"""Native WhiteBoard window that hosts the UI in WebView2.

Uses only the Python standard library and the WebView2 runtime already
installed on Windows. No pip packages and no Edge --app browser window.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import queue
import sys
import threading
import time
from ctypes import POINTER, WINFUNCTYPE, Structure, byref, c_int, c_ssize_t, c_ulong, c_void_p
from pathlib import Path
from urllib.parse import urlparse

ole32 = ctypes.windll.ole32
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32
advapi32 = ctypes.windll.advapi32
shell32 = ctypes.windll.shell32

S_OK = 0
E_NOINTERFACE = 0x80004002
E_POINTER = 0x80004003
COINIT_APARTMENTTHREADED = 0x2
WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_VISIBLE = 0x10000000
CW_USEDEFAULT = -2147483648
SW_SHOW = 5
SW_SHOWNOACTIVATE = 4
SW_HIDE = 0
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_LAYERED = 0x00080000
LWA_ALPHA = 0x02
WM_DESTROY = 0x0002
WM_SIZE = 0x0005
WM_SETFOCUS = 0x0007
WM_CLOSE = 0x0010
WM_SETICON = 0x0080
WM_RUN_SCRIPT = 0x8001
WS_POPUP = 0x80000000
WS_CHILD = 0x40000000
WS_CLIPSIBLINGS = 0x04000000
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
GCLP_HICON = -14
GCLP_HICONSM = -34
IDC_ARROW = 32512
COLOR_WINDOW = 5
HKEY_LOCAL_MACHINE = 0x80000002
HKEY_CURRENT_USER = 0x80000001
KEY_READ = 0x20019
KEY_WOW64_32KEY = 0x0200
CSIDL_APPDATA = 26

LRESULT = c_ssize_t
HRESULT = ctypes.HRESULT
WNDPROC = WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

IID_IUnknown = "{00000000-0000-0000-C000-000000000046}"
IID_ENV_DONE = "{4E8A3389-C9D8-4BD2-B6B5-124FEE6CC14D}"
IID_CTRL_DONE = "{6C4819F3-C9B7-4260-8127-C9F5BDE7F68C}"
IID_SCRIPT_DONE = "{49511172-CC67-4BCA-9923-137112F4C4CC}"
IID_WEB_MESSAGE = "{57213F19-00E6-49FA-8E3D-5B8E5A0B0B0E}"

def _resource_root() -> Path:
    import data

    return data.resource_root()


ROOT = _resource_root()
ICON_PATH = ROOT / "assets" / "logo.ico"
WEBVIEW_CLIENT = r"SOFTWARE\Microsoft\EdgeUpdate\ClientState\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
WEBVIEW_CLIENTS = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


class GUID(Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_text(cls, text: str) -> "GUID":
        value = text.strip("{}")
        parts = value.split("-")
        data4 = bytes.fromhex(parts[3] + parts[4])
        return cls(
            int(parts[0], 16),
            int(parts[1], 16),
            int(parts[2], 16),
            (ctypes.c_ubyte * 8).from_buffer_copy(data4),
        )


class RECT(Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class WNDCLASSW(Structure):
    _fields_ = [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


class MSG(Structure):
    _fields_ = [
        ("hwnd", wt.HWND),
        ("message", ctypes.c_uint),
        ("wParam", wt.WPARAM),
        ("lParam", wt.LPARAM),
        ("time", ctypes.c_uint32),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    ]


user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindow.restype = wt.BOOL
user32.MoveWindow.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.BOOL]
user32.MoveWindow.restype = wt.BOOL
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.GetMessageW.argtypes = [POINTER(MSG), wt.HWND, wt.UINT, wt.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.SetLayeredWindowAttributes.argtypes = [wt.HWND, wt.DWORD, wt.BYTE, wt.DWORD]
user32.SetLayeredWindowAttributes.restype = wt.BOOL
shell32.ExtractIconExW.argtypes = [wt.LPCWSTR, c_int, POINTER(wt.HICON), POINTER(wt.HICON), wt.UINT]
shell32.ExtractIconExW.restype = wt.UINT
shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [wt.LPCWSTR]
shell32.SetCurrentProcessExplicitAppUserModelID.restype = HRESULT


class HandlerVtbl(Structure):
    _fields_ = [
        ("QueryInterface", c_void_p),
        ("AddRef", c_void_p),
        ("Release", c_void_p),
        ("Invoke", c_void_p),
    ]


class Handler(Structure):
    _fields_ = [("lpVtbl", POINTER(HandlerVtbl)), ("kind", ctypes.c_int)]


QI_FN = WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p))
REF_FN = WINFUNCTYPE(c_ulong, c_void_p)
INVOKE_FN = WINFUNCTYPE(HRESULT, c_void_p, HRESULT, c_void_p)
EXEC_SCRIPT = WINFUNCTYPE(HRESULT, c_void_p, wt.LPCWSTR, c_void_p)
CREATE_CTRL = WINFUNCTYPE(HRESULT, c_void_p, c_void_p, c_void_p)
PUT_VISIBLE = WINFUNCTYPE(HRESULT, c_void_p, ctypes.c_int)
PUT_BOUNDS = WINFUNCTYPE(HRESULT, c_void_p, RECT)
GET_WEBVIEW = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_void_p))
NAVIGATE = WINFUNCTYPE(HRESULT, c_void_p, wt.LPCWSTR)
GET_SOURCE = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_void_p))
MOVE_FOCUS = WINFUNCTYPE(HRESULT, c_void_p, ctypes.c_int)
CLOSE_CTRL = WINFUNCTYPE(HRESULT, c_void_p)
ADDREF = WINFUNCTYPE(c_ulong, c_void_p)
POST_MSG = WINFUNCTYPE(HRESULT, c_void_p, wt.LPCWSTR)
ADD_WEB_MESSAGE = WINFUNCTYPE(HRESULT, c_void_p, c_void_p)
TRY_WEB_MESSAGE = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_void_p))
MSG_INVOKE = WINFUNCTYPE(HRESULT, c_void_p, c_void_p, c_void_p)
ole32.CoTaskMemFree.argtypes = [c_void_p]
ole32.CoTaskMemFree.restype = None

_keep: list[object] = []
_state: dict[str, object] = {}
_ui_queue: queue.Queue = queue.Queue()
_script_lock = threading.Lock()


def _guid_text(guid: GUID) -> str:
    data4 = bytes(guid.Data4)
    return (
        f"{{{guid.Data1:08X}-{guid.Data2:04X}-{guid.Data3:04X}-"
        f"{data4[0]:02X}{data4[1]:02X}-{data4[2:8].hex().upper()}}}"
    )


def _vtable_slot(interface: int, index: int) -> int:
    vtbl = ctypes.cast(interface, POINTER(c_void_p)).contents.value
    return ctypes.cast(vtbl + index * ctypes.sizeof(c_void_p), POINTER(c_void_p)).contents.value


def _query_interface(this: int, riid, ppv) -> int:
    if not ppv:
        return E_POINTER
    handler = ctypes.cast(this, POINTER(Handler)).contents
    wanted = _guid_text(riid.contents).upper()
    accepted = {IID_IUnknown}
    if handler.kind == 0:
        accepted.add(IID_ENV_DONE)
    elif handler.kind == 2:
        accepted.add(IID_SCRIPT_DONE)
    elif handler.kind == 4:
        accepted.add(IID_WEB_MESSAGE)
    else:
        accepted.add(IID_CTRL_DONE)
    if wanted in accepted:
        ppv[0] = this
        return S_OK
    ppv[0] = None
    return E_NOINTERFACE


def _add_ref(_this: int) -> int:
    return 1


def _release(_this: int) -> int:
    return 1


def _invoke(this: int, error: int, result: int) -> int:
    handler = ctypes.cast(this, POINTER(Handler)).contents
    if handler.kind == 2:
        _finish_script(error, result)
        return S_OK
    if handler.kind == 5:
        if error >= 0 and result:
            _on_popup(result, this)
        return S_OK
    if handler.kind == 6:
        if error >= 0 and result:
            _on_strip(result, this)
        return S_OK
    if error < 0 or not result:
        _state["error"] = f"WebView2 failed (0x{error & 0xFFFFFFFF:08X})"
        return S_OK
    if handler.kind == 0:
        _on_environment(result)
    else:
        _on_controller(result, hidden=handler.kind == 3)
    return S_OK


def _on_environment(environment: int) -> None:
    ADDREF(_vtable_slot(environment, 1))(environment)
    _state["environment"] = environment
    hwnd = _state["hwnd"]
    handler = _state["ctrl_handler"]
    hr = CREATE_CTRL(_vtable_slot(environment, 3))(environment, hwnd, ctypes.addressof(handler))
    if hr < 0:
        _state["error"] = f"Could not attach WebView2 (0x{hr & 0xFFFFFFFF:08X})"


def _create_hidden_window() -> int:
    """Invisible owned popup. It does not appear on screen or in the taskbar."""
    instance = kernel32.GetModuleHandleW(None)
    owner = int(_state.get("hwnd") or 0) or None
    hwnd = user32.CreateWindowExW(
        WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED,
        "WhiteBoardWindow",
        "",
        WS_POPUP,
        -32000,
        -32000,
        16,
        16,
        owner,
        None,
        instance,
        None,
    )
    if hwnd:
        user32.SetLayeredWindowAttributes(hwnd, 0, 0, LWA_ALPHA)
        user32.SetWindowPos(hwnd, None, -32000, -32000, 16, 16, 0)
        user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    return hwnd


def _on_controller(controller: int, hidden: bool = False) -> None:
    ADDREF(_vtable_slot(controller, 1))(controller)
    webview = c_void_p()
    GET_WEBVIEW(_vtable_slot(controller, 25))(controller, byref(webview))
    if not webview.value:
        _state["error"] = "WebView2 created without a view."
        return
    ADDREF(_vtable_slot(webview.value, 1))(webview.value)
    if hidden:
        _state["bb_controller"] = controller
        _state["bb_webview"] = webview.value
        try:
            PUT_VISIBLE(_vtable_slot(controller, 4))(controller, 1)
            PUT_BOUNDS(_vtable_slot(controller, 6))(controller, RECT(0, 0, 1280, 900))
        except OSError:
            pass
        hwnd = int(_state.get("bb_hwnd") or 0)
        if hwnd:
            user32.SetLayeredWindowAttributes(hwnd, 0, 0, LWA_ALPHA)
            user32.SetWindowPos(hwnd, None, -32000, -32000, 16, 16, 0)
        ready = _state.get("bb_ready")
        if isinstance(ready, threading.Event):
            ready.set()
        return
    _state["controller"] = controller
    _state["webview"] = webview.value
    ready = _state.get("app_ready")
    if isinstance(ready, threading.Event):
        ready.set()
    PUT_VISIBLE(_vtable_slot(controller, 4))(controller, 1)
    _resize()
    _hook_messages(int(webview.value))
    NAVIGATE(_vtable_slot(webview.value, 5))(webview.value, str(_state["url"]))
    MOVE_FOCUS(_vtable_slot(controller, 12))(controller, 0)
    hwnd = _state.get("hwnd")
    icons = _state.get("icons") or (0, 0)
    if hwnd:
        _apply_icons(int(hwnd), int(icons[0] or 0), int(icons[1] or 0))
    _queue_call(_create_bb_view)


def _resize() -> None:
    controller = _state.get("controller")
    hwnd = _state.get("hwnd")
    if not controller or not hwnd:
        return
    box = RECT()
    user32.GetClientRect(hwnd, byref(box))
    try:
        PUT_BOUNDS(_vtable_slot(int(controller), 6))(int(controller), box)
    except OSError:
        return


def _fill_controller(hwnd: int, controller: int) -> None:
    if not hwnd or not controller:
        return
    box = RECT()
    user32.GetClientRect(hwnd, byref(box))
    try:
        PUT_BOUNDS(_vtable_slot(controller, 6))(controller, box)
    except OSError:
        return


def _resize_popup(hwnd: int) -> None:
    if int(hwnd) == int(_docs.get("hwnd") or 0):
        _layout_docs()
        return
    if int(hwnd) == int(_docs.get("strip_hwnd") or 0):
        _fill_controller(int(hwnd), int(_docs.get("strip_controller") or 0))
        return
    for tab in list(_docs.get("tabs") or []):
        if int(tab.get("hwnd") or 0) == int(hwnd):
            _fill_controller(int(hwnd), int(tab.get("controller") or 0))
            return
    for popup in list(_state.get("popups") or []):
        if int(popup.get("hwnd") or 0) != int(hwnd):
            continue
        controller = int(popup.get("controller") or 0)
        if not controller:
            return
        box = RECT()
        user32.GetClientRect(hwnd, byref(box))
        try:
            PUT_BOUNDS(_vtable_slot(controller, 6))(controller, box)
        except OSError:
            return


def _drop_popup(hwnd: int) -> None:
    popups = list(_state.get("popups") or [])
    _state["popups"] = [popup for popup in popups if int(popup.get("hwnd") or 0) != int(hwnd)]


def _hook_messages(webview: int) -> None:
    handler = _make_message_handler()
    _state["msg_handler"] = handler
    hr = ADD_WEB_MESSAGE(_vtable_slot(webview, 34))(webview, ctypes.addressof(handler))
    if hr < 0:
        _state["error"] = f"Could not connect the window (0x{hr & 0xFFFFFFFF:08X})"


def _make_message_handler() -> Handler:
    qi = QI_FN(_query_interface)
    add = REF_FN(_add_ref)
    release = REF_FN(_release)
    invoke = MSG_INVOKE(_on_web_message)
    vtbl = HandlerVtbl(
        ctypes.cast(qi, c_void_p),
        ctypes.cast(add, c_void_p),
        ctypes.cast(release, c_void_p),
        ctypes.cast(invoke, c_void_p),
    )
    _keep.extend((qi, add, release, invoke, vtbl))
    handler = Handler(ctypes.pointer(vtbl), 4)
    _keep.append(handler)
    return handler


def _web_message_text(args: int) -> str:
    pointer = c_void_p()
    hr = TRY_WEB_MESSAGE(_vtable_slot(args, 5))(args, byref(pointer))
    if hr < 0 or not pointer.value:
        return ""
    try:
        return ctypes.wstring_at(pointer.value)
    finally:
        ole32.CoTaskMemFree(pointer)


def _on_web_message(_this: int, _sender: int, args: int) -> int:
    raw = _web_message_text(args) if args else ""
    try:
        message = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return S_OK
    if not isinstance(message, dict):
        return S_OK
    if message.get("kind") == "tabs":
        _queue_call(lambda: _handle_tab_action(message))
        return S_OK
    request_id = message.get("id")
    path = str(message.get("path") or "")
    body = message.get("body") if isinstance(message.get("body"), dict) else {}

    def work() -> None:
        try:
            bridge = _state.get("bridge")
            if not callable(bridge):
                raise RuntimeError("The WhiteBoard window is not ready.")
            payload = bridge(path, body)
            post_page(json.dumps({"id": request_id, "body": payload}))
        except Exception as exc:
            post_page(json.dumps({"id": request_id, "error": str(exc) or "Request failed."}))

    threading.Thread(target=work, daemon=True, name="wb-bridge").start()
    return S_OK


def post_page(text: str) -> None:
    """Send a reply to the visible window. Must run on the window thread."""

    def work() -> None:
        web = int(_state.get("webview") or 0)
        if not web:
            return
        POST_MSG(_vtable_slot(web, 33))(web, text)

    _queue_call(work)


def set_bridge(fn) -> None:
    _state["bridge"] = fn


def open_document(url: str, title: str = "") -> None:
    """Open a Blackboard page as a tab in the shared document window."""
    if not url:
        return

    def work() -> None:
        _ensure_doc_window()
        tab_id = str(_docs["next_id"])
        _docs["next_id"] += 1
        _docs["tabs"].append(
            {
                "id": tab_id,
                "title": (title or "Blackboard")[:80],
                "url": url,
                "controller": 0,
                "webview": 0,
            }
        )
        _docs["active"] = tab_id
        _publish_tabs()
        _create_tab_view(tab_id, url)
        user32.SetWindowTextW(int(_docs.get("hwnd") or 0), title or "WhiteBoard")

    _queue_call(work)


_popup_urls: dict[int, str] = {}
_popup_hwnds: dict[int, int] = {}
_popup_tabs: dict[int, str] = {}
_docs: dict[str, object] = {
    "hwnd": 0,
    "tabs": [],
    "active": "",
    "strip_controller": 0,
    "strip_webview": 0,
    "next_id": 1,
}
_TAB_HEIGHT = 42


def _ensure_doc_window() -> None:
    hwnd = int(_docs.get("hwnd") or 0)
    if hwnd and user32.IsWindow(hwnd):
        user32.ShowWindow(hwnd, SW_SHOW)
        return
    env = int(_state.get("environment") or 0)
    if not env:
        return
    instance = kernel32.GetModuleHandleW(None)
    hwnd = user32.CreateWindowExW(
        0,
        "WhiteBoardWindow",
        "WhiteBoard",
        WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        1100,
        760,
        None,
        None,
        instance,
        None,
    )
    if not hwnd:
        return
    icons = _state.get("icons") or (0, 0)
    _apply_icons(int(hwnd), int(icons[0] or 0), int(icons[1] or 0))
    user32.ShowWindow(hwnd, SW_SHOW)
    _docs["hwnd"] = int(hwnd)
    _docs["tabs"] = []
    _docs["strip_controller"] = 0
    _docs["strip_webview"] = 0
    strip = _child_pane(int(hwnd), 0, 0, 1100, _TAB_HEIGHT)
    _docs["strip_hwnd"] = strip
    if not strip:
        return
    handler = _make_handler(6)
    token = ctypes.addressof(handler)
    hr = CREATE_CTRL(_vtable_slot(env, 3))(env, strip, token)
    if hr < 0:
        user32.DestroyWindow(hwnd)
        _docs["hwnd"] = 0


def _child_pane(parent: int, x: int, y: int, width: int, height: int) -> int:
    instance = kernel32.GetModuleHandleW(None)
    hwnd = user32.CreateWindowExW(
        0,
        "WhiteBoardWindow",
        "",
        WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS,
        x,
        y,
        max(width, 1),
        max(height, 1),
        parent,
        None,
        instance,
        None,
    )
    return int(hwnd or 0)


def _create_tab_view(tab_id: str, url: str) -> None:
    env = int(_state.get("environment") or 0)
    parent = int(_docs.get("hwnd") or 0)
    if not env or not parent:
        return
    box = _doc_box()
    width = max(1, box.right - box.left)
    height = max(1, (box.bottom - box.top) - _TAB_HEIGHT)
    pane = _child_pane(parent, 0, _TAB_HEIGHT, width, height)
    for tab in list(_docs.get("tabs") or []):
        if tab.get("id") == tab_id:
            tab["hwnd"] = pane
            break
    if not pane:
        return
    handler = _make_handler(5)
    token = ctypes.addressof(handler)
    _popup_urls[token] = url
    _popup_tabs[token] = tab_id
    CREATE_CTRL(_vtable_slot(env, 3))(env, pane, token)


def _doc_box() -> RECT:
    box = RECT()
    hwnd = int(_docs.get("hwnd") or 0)
    if hwnd:
        user32.GetClientRect(hwnd, byref(box))
    return box


def _layout_docs() -> None:
    hwnd = int(_docs.get("hwnd") or 0)
    if not hwnd:
        return
    box = _doc_box()
    width = max(0, box.right - box.left)
    height = max(0, box.bottom - box.top)
    strip_hwnd = int(_docs.get("strip_hwnd") or 0)
    if strip_hwnd:
        user32.MoveWindow(strip_hwnd, 0, 0, width, _TAB_HEIGHT, True)
    active = str(_docs.get("active") or "")
    for tab in list(_docs.get("tabs") or []):
        pane = int(tab.get("hwnd") or 0)
        if not pane:
            continue
        visible = tab.get("id") == active
        user32.ShowWindow(pane, SW_SHOW if visible else SW_HIDE)
        if visible:
            user32.MoveWindow(pane, 0, _TAB_HEIGHT, width, max(1, height - _TAB_HEIGHT), True)


def _publish_tabs() -> None:
    web = int(_docs.get("strip_webview") or 0)
    if not web:
        return
    active = str(_docs.get("active") or "")
    payload = {
        "event": "tabs",
        "tabs": [
            {
                "id": tab.get("id"),
                "title": tab.get("title") or "Blackboard",
                "active": tab.get("id") == active,
            }
            for tab in list(_docs.get("tabs") or [])
        ],
    }
    POST_MSG(_vtable_slot(web, 33))(web, json.dumps(payload))


def _handle_tab_action(message: dict) -> None:
    action = str(message.get("action") or "")
    tab_id = str(message.get("id") or "")
    if action == "ready":
        _publish_tabs()
        _layout_docs()
        return
    if action == "activate" and any(tab.get("id") == tab_id for tab in list(_docs.get("tabs") or [])):
        _docs["active"] = tab_id
        title = next((tab.get("title") for tab in _docs["tabs"] if tab.get("id") == tab_id), "WhiteBoard")
        user32.SetWindowTextW(int(_docs.get("hwnd") or 0), str(title or "WhiteBoard"))
        _layout_docs()
        _publish_tabs()
        return
    if action == "close":
        _close_doc_tab(tab_id)


def _close_doc_tab(tab_id: str) -> None:
    tabs = list(_docs.get("tabs") or [])
    chosen = next((tab for tab in tabs if tab.get("id") == tab_id), None)
    if chosen is None:
        return
    controller = int(chosen.get("controller") or 0)
    pane = int(chosen.get("hwnd") or 0)
    if controller:
        try:
            CLOSE_CTRL(_vtable_slot(controller, 24))(controller)
        except OSError:
            pass
    if pane:
        user32.DestroyWindow(pane)
    tabs = [tab for tab in tabs if tab.get("id") != tab_id]
    _docs["tabs"] = tabs
    if not tabs:
        hwnd = int(_docs.get("hwnd") or 0)
        _docs["hwnd"] = 0
        _docs["active"] = ""
        _docs["strip_controller"] = 0
        _docs["strip_webview"] = 0
        if hwnd:
            user32.DestroyWindow(hwnd)
        return
    if _docs.get("active") == tab_id:
        _docs["active"] = tabs[-1].get("id")
    _layout_docs()
    _publish_tabs()


def _on_popup(controller: int, token: int) -> None:
    ADDREF(_vtable_slot(controller, 1))(controller)
    webview = c_void_p()
    GET_WEBVIEW(_vtable_slot(controller, 25))(controller, byref(webview))
    if not webview.value:
        return
    ADDREF(_vtable_slot(webview.value, 1))(webview.value)
    tab_id = _popup_tabs.pop(token, "")
    url = _popup_urls.pop(token, "")
    _popup_hwnds.pop(token, 0)
    chosen = None
    for tab in list(_docs.get("tabs") or []):
        if tab.get("id") == tab_id:
            tab["controller"] = controller
            tab["webview"] = webview.value
            chosen = tab
            break
    if url:
        NAVIGATE(_vtable_slot(webview.value, 5))(webview.value, url)
        _retry_tab_navigation(tab_id, url)
    if chosen is not None:
        _fill_controller(int(chosen.get("hwnd") or 0), controller)
    _layout_docs()


def _retry_tab_navigation(tab_id: str, url: str) -> None:
    """Open the assignment again if the tab fell back to the Blackboard home page."""

    def attempt(delay: float, left: int) -> None:
        def later() -> None:
            def work() -> None:
                tab = next((item for item in list(_docs.get("tabs") or []) if item.get("id") == tab_id), None)
                web = int((tab or {}).get("webview") or 0)
                if not web or not url:
                    return
                href = _webview_source(web)
                if href and not _is_home_page(href):
                    return
                NAVIGATE(_vtable_slot(web, 5))(web, url)
                if left > 0:
                    attempt(1.6, left - 1)

            _queue_call(work)

        threading.Timer(delay, later).start()

    attempt(1.2, 2)


def _webview_source(web: int) -> str:
    pointer = c_void_p()
    try:
        hr = GET_SOURCE(_vtable_slot(web, 4))(web, byref(pointer))
    except OSError:
        return ""
    if hr < 0 or not pointer.value:
        return ""
    try:
        return ctypes.wstring_at(pointer.value)
    finally:
        ole32.CoTaskMemFree(pointer)


def _is_home_page(url: str) -> bool:
    path = (urlparse(url).path or "/").rstrip("/").lower() or "/"
    if path in {
        "/",
        "/ultra",
        "/ultra/stream",
        "/ultra/course",
        "/ultra/institution",
        "/ultra/institution-page",
    }:
        return True
    if path.startswith("/webapps/portal"):
        return True
    if path.startswith("/ultra"):
        return True
    return False


def _on_strip(controller: int, token: int) -> None:
    ADDREF(_vtable_slot(controller, 1))(controller)
    webview = c_void_p()
    GET_WEBVIEW(_vtable_slot(controller, 25))(controller, byref(webview))
    if not webview.value:
        return
    ADDREF(_vtable_slot(webview.value, 1))(webview.value)
    _popup_hwnds.pop(token, 0)
    _docs["strip_controller"] = controller
    _docs["strip_webview"] = webview.value
    _hook_messages(int(webview.value))
    page = (ROOT / "static" / "tabs.html").as_uri()
    PUT_VISIBLE(_vtable_slot(controller, 4))(controller, 1)
    _fill_controller(int(_docs.get("strip_hwnd") or 0), controller)
    NAVIGATE(_vtable_slot(webview.value, 5))(webview.value, page)
    _layout_docs()


def _close_controller() -> None:
    controller = _state.get("controller")
    if not controller:
        return
    CLOSE_CTRL(_vtable_slot(int(controller), 24))(int(controller))
    _state["controller"] = None


def _wndproc(hwnd, message, wparam, lparam) -> int:
    main = int(_state.get("hwnd") or 0)
    if message == WM_RUN_SCRIPT:
        _state["ui_pending"] = True
        return 0
    if message == WM_SIZE:
        if hwnd == main:
            _resize()
        else:
            _resize_popup(hwnd)
        return 0
    if message == WM_SETFOCUS and hwnd == main:
        controller = _state.get("controller")
        if controller:
            try:
                MOVE_FOCUS(_vtable_slot(int(controller), 12))(int(controller), 0)
            except OSError:
                return 0
        return 0
    if message == WM_CLOSE:
        if hwnd == main:
            _close_controller()
        user32.DestroyWindow(hwnd)
        return 0
    if message == WM_DESTROY:
        _drop_popup(hwnd)
        if int(hwnd) == int(_docs.get("hwnd") or 0):
            _docs["hwnd"] = 0
            _docs["tabs"] = []
            _docs["strip_controller"] = 0
            _docs["strip_webview"] = 0
        if hwnd == main:
            user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, message, wparam, lparam)


def _make_handler(kind: int) -> Handler:
    qi = QI_FN(_query_interface)
    add = REF_FN(_add_ref)
    release = REF_FN(_release)
    invoke = INVOKE_FN(_invoke)
    vtbl = HandlerVtbl(
        ctypes.cast(qi, c_void_p),
        ctypes.cast(add, c_void_p),
        ctypes.cast(release, c_void_p),
        ctypes.cast(invoke, c_void_p),
    )
    _keep.extend((qi, add, release, invoke, vtbl))
    handler = Handler(ctypes.pointer(vtbl), kind)
    _keep.append(handler)
    return handler


def _reg_read(root: int, subkey: str, name: str) -> str:
    key = wt.HKEY()
    if advapi32.RegOpenKeyExW(root, subkey, 0, KEY_READ | KEY_WOW64_32KEY, byref(key)):
        return ""
    size = wt.DWORD(0)
    if advapi32.RegQueryValueExW(key, name, None, None, None, byref(size)) or not size.value:
        advapi32.RegCloseKey(key)
        return ""
    buf = ctypes.create_unicode_buffer(size.value // 2 + 1)
    advapi32.RegQueryValueExW(key, name, None, None, buf, byref(size))
    advapi32.RegCloseKey(key)
    return buf.value.strip("\x00")


def _runtime_dll() -> Path:
    for root, key, name in (
        (HKEY_LOCAL_MACHINE, WEBVIEW_CLIENT, "EBWebView"),
        (HKEY_CURRENT_USER, WEBVIEW_CLIENT, "EBWebView"),
    ):
        folder = _reg_read(root, key, name)
        if folder:
            candidate = Path(folder) / "EBWebView" / "x64" / "EmbeddedBrowserWebView.dll"
            if candidate.is_file():
                return candidate
    version = _reg_read(HKEY_LOCAL_MACHINE, WEBVIEW_CLIENTS, "pv")
    location = _reg_read(HKEY_LOCAL_MACHINE, WEBVIEW_CLIENTS, "location")
    if version and location:
        candidate = Path(location) / version / "EBWebView" / "x64" / "EmbeddedBrowserWebView.dll"
        if candidate.is_file():
            return candidate
    roots = [
        Path(r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application"),
        Path(r"C:\Program Files\Microsoft\EdgeWebView\Application"),
    ]
    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        found.extend(root.glob("*/EBWebView/x64/EmbeddedBrowserWebView.dll"))
    if not found:
        raise FileNotFoundError("Microsoft Edge WebView2 Runtime is not installed.")
    return sorted(found)[-1]


def _user_data() -> str:
    import data

    data.install()
    data.WEBVIEW_PATH.mkdir(parents=True, exist_ok=True)
    return str(data.WEBVIEW_PATH)


def _claim_app_id() -> None:
    try:
        shell32.SetCurrentProcessExplicitAppUserModelID("WhiteBoard")
    except Exception:
        return


def _load_icons() -> tuple[int, int]:
    if not ICON_PATH.is_file():
        return 0, 0
    path = str(ICON_PATH)
    large = wt.HICON()
    small = wt.HICON()
    extracted = shell32.ExtractIconExW(path, 0, byref(large), byref(small), 1)
    big = int(large.value or 0) if extracted else 0
    tiny = int(small.value or 0) if extracted else 0
    if not big:
        big = user32.LoadImageW(None, path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
    if not tiny:
        tiny = user32.LoadImageW(None, path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
    if not big:
        big = user32.LoadImageW(None, path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
    return big, tiny


def _apply_icons(hwnd: int, large: int, small: int) -> None:
    if large:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, large)
        user32.SetClassLongPtrW(hwnd, GCLP_HICON, large)
    if small:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small)
        user32.SetClassLongPtrW(hwnd, GCLP_HICONSM, small)


def _create_window() -> int:
    instance = kernel32.GetModuleHandleW(None)
    large, small = _load_icons()
    _state["icons"] = (large, small)
    wndproc = WNDPROC(_wndproc)
    _keep.append(wndproc)
    clazz = WNDCLASSW()
    clazz.lpfnWndProc = wndproc
    clazz.hInstance = instance
    clazz.hIcon = large or small
    clazz.hCursor = user32.LoadCursorW(None, IDC_ARROW)
    clazz.hbrBackground = gdi32.GetStockObject(0)
    clazz.lpszClassName = "WhiteBoardWindow"
    atom = user32.RegisterClassW(byref(clazz))
    if not atom:
        raise OSError("Could not register the WhiteBoard window class.")
    hwnd = user32.CreateWindowExW(
        0,
        "WhiteBoardWindow",
        "WhiteBoard",
        WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        1280,
        840,
        None,
        None,
        instance,
        None,
    )
    if not hwnd:
        raise OSError("Could not create the WhiteBoard window.")
    _apply_icons(hwnd, large, small)
    user32.ShowWindow(hwnd, SW_SHOW)
    user32.UpdateWindow(hwnd)
    return hwnd


def _create_webview() -> None:
    dll_path = _runtime_dll()
    dll = ctypes.WinDLL(str(dll_path))
    create = dll.CreateWebViewEnvironmentWithOptionsInternal
    create.argtypes = [wt.BOOL, c_int, wt.LPCWSTR, c_void_p, c_void_p]
    create.restype = HRESULT
    env_handler = _make_handler(0)
    ctrl_handler = _make_handler(1)
    _state["ctrl_handler"] = ctrl_handler
    _state["bb_handler"] = _make_handler(3)
    _state["script_handler"] = _make_handler(2)
    _state["app_ready"] = threading.Event()
    _state["bb_ready"] = threading.Event()
    hr = create(1, 0, _user_data(), None, ctypes.addressof(env_handler))
    if hr < 0:
        raise OSError(f"Could not start WebView2 (0x{hr & 0xFFFFFFFF:08X})")


def _queue_call(fn) -> None:
    _ui_queue.put(("call", fn))
    hwnd = int(_state.get("hwnd") or 0)
    if hwnd:
        user32.PostMessageW(hwnd, WM_RUN_SCRIPT, 0, 0)


def _create_bb_view() -> None:
    """Second WebView2 for Blackboard, so the dashboard page stays open."""
    if _state.get("bb_webview") or _state.get("bb_starting"):
        return
    _state["bb_starting"] = True
    hwnd = _create_hidden_window()
    if not hwnd:
        _state["bb_error"] = "Could not open the Blackboard browser."
        ready = _state.get("bb_ready")
        if isinstance(ready, threading.Event):
            ready.set()
        return
    _state["bb_hwnd"] = hwnd
    env = int(_state.get("environment") or 0)
    handler = _state.get("bb_handler")
    if not env or handler is None:
        _state["bb_error"] = "Could not attach the Blackboard browser."
        ready = _state.get("bb_ready")
        if isinstance(ready, threading.Event):
            ready.set()
        return
    hr = CREATE_CTRL(_vtable_slot(env, 3))(env, hwnd, ctypes.addressof(handler))
    if hr < 0:
        _state["bb_error"] = f"Could not attach the Blackboard browser (0x{hr & 0xFFFFFFFF:08X})"
        ready = _state.get("bb_ready")
        if isinstance(ready, threading.Event):
            ready.set()


def _pump_ui() -> None:
    job = None
    if not _state.get("script_busy"):
        try:
            job = _ui_queue.get_nowait()
        except queue.Empty:
            return
    else:
        # Keep page scripts from blocking window calls such as navigation.
        held: list[object] = []
        while True:
            try:
                item = _ui_queue.get_nowait()
            except queue.Empty:
                break
            if item[0] == "call":
                job = item
                break
            held.append(item)
        for item in held:
            _ui_queue.put(item)
        if job is None:
            return
    kind = job[0]
    if kind == "call":
        job[1]()
        user32.PostMessageW(int(_state.get("hwnd") or 0), WM_RUN_SCRIPT, 0, 0)
        return
    _expression, box, done = job[1], job[2], job[3]
    target = job[4] if len(job) > 4 else "bb"
    webview = _state.get("webview" if target == "page" else "bb_webview")
    if not webview:
        box["error"] = "The Blackboard sign-in window is not ready."
        done.set()
        user32.PostMessageW(int(_state.get("hwnd") or 0), WM_RUN_SCRIPT, 0, 0)
        return
    _state["script_busy"] = True
    _state["script_box"] = box
    _state["script_done"] = done
    buf = ctypes.create_unicode_buffer(_expression)
    _state["script_buf"] = buf
    handler = _state["script_handler"]
    try:
        hr = EXEC_SCRIPT(_vtable_slot(int(webview), 29))(int(webview), buf, ctypes.addressof(handler))
    except OSError as exc:
        hr = -1
        box["error"] = str(exc)
    if hr < 0:
        _state["script_busy"] = False
        box.setdefault("error", f"Could not run the Blackboard page (0x{hr & 0xFFFFFFFF:08X})")
        done.set()
        user32.PostMessageW(int(_state.get("hwnd") or 0), WM_RUN_SCRIPT, 0, 0)


def _finish_script(error: int, result_ptr: int) -> None:
    box = _state.get("script_box")
    done = _state.get("script_done")
    if not isinstance(box, dict):
        _state["script_busy"] = False
        return
    if box.get("gen") != _state.get("script_gen"):
        _state["script_busy"] = False
        return
    try:
        if error < 0:
            box["error"] = f"Blackboard page failed (0x{error & 0xFFFFFFFF:08X})"
        elif result_ptr:
            raw = ctypes.wstring_at(result_ptr)
            box["value"] = json.loads(raw) if raw else None
        else:
            box["value"] = None
    except Exception as exc:
        box["error"] = str(exc)
    finally:
        _state["script_busy"] = False
        if isinstance(done, threading.Event):
            done.set()
        hwnd = int(_state.get("hwnd") or 0)
        if hwnd:
            user32.PostMessageW(hwnd, WM_RUN_SCRIPT, 0, 0)


def wait_browser(timeout: float = 30) -> None:
    """Wait until the separate Blackboard view can load pages."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _state.get("bb_error") and not _state.get("bb_webview"):
            raise RuntimeError(str(_state["bb_error"]))
        ready = _state.get("bb_ready")
        if isinstance(ready, threading.Event) and ready.is_set() and _state.get("bb_webview"):
            return
        time.sleep(0.05)
    raise RuntimeError("The Blackboard sign-in window is not ready.")


def set_title(text: str) -> None:
    hwnd = int(_state.get("hwnd") or 0)
    if hwnd:
        user32.SetWindowTextW(hwnd, text)


def navigate_bb(url: str) -> None:
    wait_browser()
    done = threading.Event()
    box: dict[str, object] = {}

    def work() -> None:
        try:
            web = int(_state["bb_webview"])
            NAVIGATE(_vtable_slot(web, 5))(web, url)
        except OSError as exc:
            box["error"] = str(exc)
        finally:
            done.set()

    _ui_queue.put(("call", work))
    user32.PostMessageW(int(_state["hwnd"]), WM_RUN_SCRIPT, 0, 0)
    if not done.wait(20):
        raise TimeoutError("Could not open Blackboard.")
    if box.get("error"):
        raise RuntimeError(str(box["error"]))


def return_to_app() -> None:
    """The dashboard never left this window. Clear the status title."""
    set_title("WhiteBoard")


def eval_page(expression: str, timeout: float = 20):
    """Run JavaScript in the visible WhiteBoard window."""
    deadline = time.time() + timeout
    while time.time() < deadline and not _state.get("webview"):
        time.sleep(0.05)
    if not _state.get("webview"):
        raise RuntimeError("The WhiteBoard window is not ready.")
    return _eval_js(expression, timeout, target="page")


def eval_js(expression: str, timeout: float = 20):
    wait_browser(timeout=min(timeout, 25))
    return _eval_js(expression, timeout, target="bb")


def _eval_js(expression: str, timeout: float, *, target: str):
    """Run one page script. A second script waits until this one finishes.

    Timing out and sending another ExecuteScript while the first is still
    running leaves the hidden Blackboard view stuck, so refresh never leaves
    "Loading files".
    """
    if not _script_lock.acquire(timeout=timeout):
        raise TimeoutError("Blackboard took too long to answer.")
    try:
        done = threading.Event()
        box: dict[str, object] = {}
        generation = int(_state.get("script_gen") or 0) + 1
        _state["script_gen"] = generation
        box["gen"] = generation
        _ui_queue.put(("script", expression, box, done, target))
        user32.PostMessageW(int(_state["hwnd"]), WM_RUN_SCRIPT, 0, 0)
        if not done.wait(timeout):
            # Stay on this script until its callback arrives so the next
            # caller cannot pile another ExecuteScript on top of it.
            done.wait(8)
        if not done.is_set():
            if _state.get("script_gen") == generation:
                _state["script_busy"] = False
                _state["script_box"] = None
            raise TimeoutError("Blackboard took too long to answer.")
        if box.get("error"):
            raise RuntimeError(str(box["error"]))
        return box.get("value")
    finally:
        _script_lock.release()


def open_window(url: str) -> None:
    """Create a WhiteBoard window and load the local UI."""
    if sys.platform != "win32":
        raise RuntimeError("The WhiteBoard window host is Windows-only.")
    bridge = _state.get("bridge")
    _state.clear()
    if callable(bridge):
        _state["bridge"] = bridge
    _state["url"] = url
    _claim_app_id()
    hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if hr < 0 and hr & 0xFFFFFFFF != 0x80010106:  # RPC_E_CHANGED_MODE
        raise OSError(f"COM did not start (0x{hr & 0xFFFFFFFF:08X})")
    try:
        hwnd = _create_window()
        _state["hwnd"] = hwnd
        _create_webview()
        msg = MSG()
        while user32.GetMessageW(byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))
            if _state.get("ui_pending"):
                _state["ui_pending"] = False
                _pump_ui()
            if _state.get("error"):
                user32.MessageBoxW(hwnd, str(_state["error"]), "WhiteBoard", 0x10)
                _state["error"] = None
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    finally:
        _close_controller()
        ole32.CoUninitialize()
