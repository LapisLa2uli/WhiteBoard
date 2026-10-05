"""Native WhiteBoard window that hosts the UI in WKWebView.

Mirrors ``host._windows``: one visible view for the dashboard, one hidden view
that holds the signed-in Blackboard session, and a queue that keeps every
WebKit call on the Cocoa main thread.

Two differences from the Windows backend are deliberate.

*Storage.* WebKit picks the disk location for its default website data store
(``~/Library/WebKit/<bundle-id>/``) and offers no way to move it, which would
leave a folder in the user's Library that the app cannot clean up. Instead this
backend uses a non-persistent store and keeps the cookie jar in the app's own
data folder, so ``~/.config/whiteboard`` stays the only place anything is kept.

*Threading.* There is no message pump to post to, so cross-thread calls go
through ``performSelectorOnMainThread:``. Script execution keeps the one-lock
serialisation the Windows host uses: two overlapping ``ExecuteScript`` calls
leave the hidden view wedged.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.parse import quote

import AppKit
import Foundation
import WebKit
from Foundation import NSObject

import objc


def _resource_root() -> Path:
    import data

    return data.resource_root()


ROOT = _resource_root()
ICON_PATH = ROOT / "assets" / "AppIcon.icns"

_APP_NAME = "WhiteBoard"
_STRIP_HEIGHT = 42
_TAB_FRAME = Foundation.NSMakeRect(-32000, -32000, 1280, 900)

# Autoresizing masks. Using these means the tab strip and every document view
# follow the window when it is resized, so no resize callback is needed.
_MASK_W = AppKit.NSViewWidthSizable
_MASK_H = AppKit.NSViewHeightSizable
_MASK_TOP = AppKit.NSViewMinYMargin

# Strong references. WebKit crashes if a script message handler is collected
# while the page can still post to it, and ObjC blocks must outlive the call
# that made them.
_keep: list[object] = []
_state: dict[str, object] = {}
_docs: dict[str, object] = {
    "window": None,
    "strip_view": None,
    "views": {},
    "tabs": [],
    "active": "",
    "next_id": 1,
}
_script_lock = threading.Lock()


# --------------------------------------------------------------------------
# JS shim
# --------------------------------------------------------------------------

# static/app.js and static/tabs.html both expect WebView2's chrome.webview API.
# WKWebView has no equivalent, so give them the same object, injected before any
# page script runs. postMessage matches WebView2's PostWebMessageAsJson: the
# Python side always hands over JSON text, and listeners receive the parsed
# value, which is exactly what app.js already handles.
_SHIM = r"""
(function () {
  var listeners = [];
  window.__wbDeliver = function (raw) {
    var data = raw;
    if (typeof raw === "string") { try { data = JSON.parse(raw); } catch (error) { data = raw; } }
    for (var i = 0; i < listeners.length; i++) {
      try { listeners[i]({ data: data }); } catch (error) { /* a bad listener must not stop the rest */ }
    }
  };
  window.chrome = window.chrome || {};
  window.chrome.webview = {
    postMessage: function (raw) {
      try {
        var text = typeof raw === "string" ? raw : JSON.stringify(raw);
        window.webkit.messageHandlers.wb.postMessage(text);
      } catch (error) { /* WebKit throws if the frame is gone mid-post */ }
    },
    addEventListener: function (type, fn) {
      if (type === "message" && typeof fn === "function") listeners.push(fn);
    },
  };
})();
"""


# --------------------------------------------------------------------------
# Objective-C plumbing
# --------------------------------------------------------------------------


class _Handler(NSObject):
    """Bridges a page's window.chrome.webview.postMessage into Python."""

    def initWithBridge_(self, bridge):
        self = objc.super(_Handler, self).init()
        if self is None:
            return None
        self.bridge = bridge
        return self

    def userContentController_didReceiveScriptMessage_(self, _controller, message):
        from host.trust import trusted_page
        frame = message.frameInfo()
        if not frame.isMainFrame() or not trusted_page(str(frame.request().URL().absoluteString())):
            return
        raw = message.body()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        self.bridge(raw if isinstance(raw, str) else str(raw))


class _AppDelegate(NSObject):
    """Closing the last window ends the app, the way a normal Mac app behaves."""

    def applicationShouldTerminateAfterLastWindowClosed_(self, _app):
        return True


class _Actions(NSObject):
    """Declares the selectors the menu bar needs.

    The bodies are never called. A stub class is the cheapest way to get a
    correctly named SEL out of pyobjc, which will not build one from a bare
    string. Every menu item is created with a nil target, so AppKit starts the
    action at the first responder and walks up the chain: that is how Copy,
    Paste and Select All reach the focused field inside the WKWebView rather
    than stopping here.
    """

    def orderFrontStandardAboutPanel_(self, _sender):
        pass

    def hide_(self, _sender):
        pass

    def hideOtherApplications_(self, _sender):
        pass

    def unhideAllApplications_(self, _sender):
        pass

    def terminate_(self, _sender):
        pass

    def undo_(self, _sender):
        pass

    def redo_(self, _sender):
        pass

    def cut_(self, _sender):
        pass

    def copy_(self, _sender):
        pass

    def paste_(self, _sender):
        pass

    def delete_(self, _sender):
        pass

    def selectAll_(self, _sender):
        pass

    def performMiniaturize_(self, _sender):
        pass

    def performZoom_(self, _sender):
        pass

    def arrangeInFront_(self, _sender):
        pass


class _Job(NSObject):
    """Carries one Python callable across a hop onto the main thread."""

    def initWithCall_(self, call):
        self = objc.super(_Job, self).init()
        if self is None:
            return None
        self.call = call
        return self

    def runOnMain_(self, _ignored):
        try:
            self.call()
        except Exception as exc:
            _state["error"] = str(exc) or exc.__class__.__name__
            # The run loop cannot let this escape, but swallowing it silently
            # turns a UI-side crash into "Blackboard took too long to answer"
            # twenty seconds later, which is close to impossible to trace.
            sys.stderr.write("WhiteBoard: window call failed: %r\n" % (exc,))
            sys.stderr.flush()


class _PageDelegate(NSObject):
    """Navigation and popup handling for both the dashboard and Blackboard views."""

    def initWithTag_(self, tag):
        self = objc.super(_PageDelegate, self).init()
        if self is None:
            return None
        self.tag = tag
        return self

    def webView_didFinishNavigation_(self, _web_view, _navigation):
        if self.tag == "page":
            event = _state.get("page_ready")
            if isinstance(event, threading.Event):
                event.set()

        else:
            event = _state.get("bb_ready")
            if isinstance(event, threading.Event):
                event.set()

    def webView_decidePolicyForNavigationAction_decisionHandler_(self, view, action, decide):
        from host.trust import trusted_page
        if self.tag in {"page", "strip"}:
            decide(1 if trusted_page(str(action.request().URL().absoluteString())) else 0)
        else:
            decide(1)

    def webView_didFailNavigation_withError_(self, _web_view, _navigation, error):
        if self.tag == "page":
            _state["error"] = "The WhiteBoard window could not load: %s" % _describe(error)

    def webView_createWebViewWithConfiguration_forNavigationAction_window_(
        self, _web_view, _configuration, action, _window
    ):
        """Blackboard opens links in a new window. Show them as a tab instead."""
        url = action.request().URL()
        if url is not None:
            open_document(str(url.absoluteString()), "Blackboard")
        return None


def _describe(error) -> str:
    if error is None:
        return ""
    try:
        return str(error.localizedDescription())
    except Exception:
        return str(error)


def _on_main(call):
    """Run ``call`` on the Cocoa main thread, blocking until it has run."""
    if AppKit.NSThread.isMainThread():
        call()
        return
    job = _Job.alloc().initWithCall_(call)
    job.performSelectorOnMainThread_withObject_waitUntilDone_(
        objc.selector(_Job.runOnMain_, signature=b"v@:"), None, True
    )


def _inject_bridge(config):
    """Install the shim and the message handler on one view's configuration."""
    handler = _Handler.alloc().initWithBridge_(_on_web_message)
    _keep.append(handler)
    controller = config.userContentController()
    controller.addScriptMessageHandler_name_(handler, "wb")
    controller.addUserScript_(
        WebKit.WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
            _SHIM, WebKit.WKUserScriptInjectionTimeAtDocumentStart, True
        )
    )


def _load(url_or_request, view):
    if isinstance(url_or_request, str):
        request = Foundation.NSURLRequest.requestWithURL_(
            Foundation.NSURL.URLWithString_(url_or_request)
        )
    else:
        request = url_or_request
    view.loadRequest_(request)


def _make_view(frame, *, bridged: bool, tag: str, store):
    config = WebKit.WKWebViewConfiguration.alloc().init()
    config.setWebsiteDataStore_(store)
    if bridged:
        _inject_bridge(config)
    delegate = _PageDelegate.alloc().initWithTag_(tag)
    _keep.append(delegate)
    view = WebKit.WKWebView.alloc().initWithFrame_configuration_(frame, config)
    view.setNavigationDelegate_(delegate)
    view.setUIDelegate_(delegate)
    _state[f"{tag}_delegate"] = delegate
    return view


def _apply_icon(window):
    image = _app_icon()
    if image is not None and window is not None:
        try:
            window.setIcon_(image)
        except Exception:
            pass


def _app_icon():
    """Load the .icns once and reuse it for the Dock and every window."""
    if not ICON_PATH.is_file():
        return None
    try:
        image = AppKit.NSImage.alloc().initWithContentsOfFile_(str(ICON_PATH))
        if image is None or not image.isValid():
            return None
        return image
    except Exception:
        return None


# --------------------------------------------------------------------------
# Menu bar
# --------------------------------------------------------------------------
#
# AppKit gives a Regular-activation-policy app a Dock tile but no menu bar, and
# without a menu bar there is no Cmd+Q and no Cmd+C/V. The Edit entries matter
# most: their targets are nil, so AppKit routes them down the responder chain,
# which is how they reach the focused field inside a WKWebView.

def _sel(name: str):
    """A menu action SEL, e.g. _sel('copy_'). Names are pyobjc style."""
    return getattr(_Actions, name)


_CMD = AppKit.NSEventModifierFlagCommand
_SHIFT = AppKit.NSEventModifierFlagShift
_OPT = AppKit.NSEventModifierFlagOption


def _item(title, action, key="", modifiers=0):
    entry = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
    if modifiers:
        entry.setKeyEquivalentModifierMask_(modifiers)
    return entry


def _separator():
    return AppKit.NSMenuItem.separatorItem()


def _menu_with(name, items):
    submenu = AppKit.NSMenu.alloc().initWithTitle_(name)
    submenu.setAutoenablesItems_(False)
    for entry in items:
        submenu.addItem_(_separator() if entry is None else entry)
    owner = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(name, None, "")
    owner.setSubmenu_(submenu)
    return owner


def _build_menu() -> None:
    app_menu = [
        _item("About WhiteBoard", _sel("orderFrontStandardAboutPanel_")),
        None,
        _item("Hide WhiteBoard", _sel("hide_"), "h", _CMD),
        _item("Hide Others", _sel("hideOtherApplications_"), "h", _CMD | _OPT),
        _item("Show All", _sel("unhideAllApplications_")),
        None,
        _item("Quit WhiteBoard", _sel("terminate_"), "q", _CMD),
    ]

    edit_menu = [
        _item("Undo", _sel("undo_"), "z", _CMD),
        _item("Redo", _sel("redo_"), "z", _CMD | _SHIFT),
        None,
        _item("Cut", _sel("cut_"), "x", _CMD),
        _item("Copy", _sel("copy_"), "c", _CMD),
        _item("Paste", _sel("paste_"), "v", _CMD),
        _item("Delete", _sel("delete_"), "", _CMD),
        _item("Select All", _sel("selectAll_"), "a", _CMD),
    ]

    window_menu = [
        _item("Minimize", _sel("performMiniaturize_"), "m", _CMD),
        _item("Zoom", _sel("performZoom_")),
        None,
        _item("Bring All to Front", _sel("arrangeInFront_")),
    ]

    main = AppKit.NSMenu.alloc().init()
    main.setAutoenablesItems_(False)
    owners = [
        _menu_with("WhiteBoard", app_menu),
        _menu_with("Edit", edit_menu),
        _menu_with("Window", window_menu),
    ]
    for owner in owners:
        main.addItem_(owner)

    application = AppKit.NSApplication.sharedApplication()
    application.setMainMenu_(main)
    # Naming the Window menu lets AppKit keep Minimize and Zoom in step with
    # whichever document is frontmost.
    try:
        application.setWindowsMenu_(owners[2].submenu())
    except Exception:
        pass


# --------------------------------------------------------------------------
# Page bridge
# --------------------------------------------------------------------------


def _on_web_message(raw: str):
    """Handle one chrome.webview.postMessage from a page."""
    try:
        message = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return None
    if not isinstance(message, dict):
        return None
    if message.get("kind") == "tabs":
        _on_main(lambda: _handle_tab_action(message))
        return None

    request_id = message.get("id")
    path = str(message.get("path") or "")
    body = message.get("body") if isinstance(message.get("body"), dict) else {}

    def work() -> None:
        try:
            bridge = _state.get("bridge")
            if not callable(bridge):
                raise RuntimeError("The WhiteBoard window is not ready.")
            post_page(json.dumps({"id": request_id, "body": bridge(path, body)}))
        except Exception as exc:
            post_page(json.dumps({"id": request_id, "error": str(exc) or "Request failed."}))

    threading.Thread(target=work, daemon=True, name="wb-bridge").start()
    return None


# --------------------------------------------------------------------------
# Public surface
# --------------------------------------------------------------------------


def set_bridge(fn) -> None:
    _state["bridge"] = fn


def set_title(text: str) -> None:
    window = _state.get("window")
    if window is None:
        return
    _on_main(lambda: window.setTitle_(str(text)))


def post_page(text: str) -> None:
    """Send a reply to the visible window. Safe to call from any thread."""
    view = _state.get("page_view")
    if view is None:
        return
    script = "window.__wbDeliver && window.__wbDeliver(%s);" % json.dumps(text)
    _on_main(lambda: view.evaluateJavaScript_completionHandler_(script, lambda _v, _e: None))


def wait_browser(timeout: float = 30) -> None:
    """Block until the hidden Blackboard view can take a script."""
    ready = _state.get("bb_ready")
    if not isinstance(ready, threading.Event):
        raise RuntimeError("The Blackboard sign-in window is not ready.")
    if not ready.wait(timeout) or not _state.get("bb_view"):
        raise RuntimeError("The Blackboard sign-in window is not ready.")


def navigate_bb(url: str) -> None:
    wait_browser()
    view = _state["bb_view"]

    def go() -> None:
        request = Foundation.NSURLRequest.requestWithURL_(Foundation.NSURL.URLWithString_(url))
        view.loadRequest_(request)

    _on_main(go)


def return_to_app() -> None:
    set_title(_APP_NAME)


def eval_page(expression: str, timeout: float = 20):
    return _eval_js(expression, timeout, target="page")


def eval_js(expression: str, timeout: float = 20):
    return _eval_js(expression, timeout, target="bb")


def _plain(value):
    """Convert a value from evaluateJavaScript into native Python.

    WKWebView's completion handler is declared with an untyped `id` argument, so
    pyobjc applies none of its default converters and hands back the raw
    Objective-C objects: a JS object arrives as __NSDictionaryM, a JS array as
    __NSArrayM, and null as NSNull rather than None.

    The Windows backend returns json.loads() output instead, and the rest of the
    app is written against that shape -- session.py tests isinstance(value, list)
    and isinstance(row, dict). Without this conversion every result fails those
    checks, so sign-in reports a missing form and every fetch is rejected.
    """
    if value is None:
        return None
    if isinstance(value, Foundation.NSNull):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return str(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, Foundation.NSDictionary):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (Foundation.NSArray, Foundation.NSSet)):
        return [_plain(item) for item in value]
    return value


def _eval_js(expression: str, timeout: float, *, target: str):
    """Run one script and wait for its result.

    The lock matters: a timed-out script that is still running would otherwise
    get a second ExecuteScript stacked on top, and the hidden view never
    recovers from that.
    """
    if not _script_lock.acquire(timeout=timeout):
        raise TimeoutError("Blackboard took too long to answer.")
    try:
        view = _state.get("page_view" if target == "page" else "bb_view")
        if view is None:
            raise RuntimeError("The WhiteBoard window is not ready.")
        box: dict[str, object] = {}
        done = threading.Event()

        def finished(value, error):
            if error is not None:
                box["error"] = _describe(error)
            else:
                box["value"] = value
            done.set()

        def run() -> None:
            view.evaluateJavaScript_completionHandler_(expression, finished)

        _on_main(run)
        if not done.wait(timeout):
            raise TimeoutError("Blackboard took too long to answer.")
        if box.get("error"):
            raise RuntimeError(str(box["error"]))
        return _plain(box.get("value"))
    finally:
        _script_lock.release()


def open_document(url: str, title: str = "") -> None:
    """Open a Blackboard page as a tab in the shared document window."""
    if not url:
        return

    def work() -> None:
        _ensure_doc_window()
        tab_id = str(_docs["next_id"])
        _docs["next_id"] = int(_docs["next_id"]) + 1
        _docs["tabs"].append(
            {"id": tab_id, "title": (title or "Blackboard")[:80], "url": url}
        )
        _docs["active"] = tab_id
        _make_tab_view(tab_id, url)
        _publish_tabs()
        _layout_docs()

    _on_main(work)


def open_window(url: str) -> None:
    """Create the WhiteBoard window and run until it closes."""
    bridge = _state.get("bridge")
    _state.clear()
    if callable(bridge):
        _state["bridge"] = bridge
    _state["page_ready"] = threading.Event()
    _state["bb_ready"] = threading.Event()
    _state["url"] = url

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)

    delegate = _AppDelegate.alloc().init()
    _keep.append(delegate)
    app.setDelegate_(delegate)
    _build_menu()

    icon = _app_icon()
    if icon is not None:
        app.setApplicationIconImage_(icon)

    _on_main(lambda: _build(url))
    app.activateIgnoringOtherApps_(True)
    app.run()


# --------------------------------------------------------------------------
# Window construction
# --------------------------------------------------------------------------


def _build(url: str) -> None:
    import data

    data.install()

    style = (
        AppKit.NSWindowStyleMaskTitled
        | AppKit.NSWindowStyleMaskClosable
        | AppKit.NSWindowStyleMaskMiniaturizable
        | AppKit.NSWindowStyleMaskResizable
    )
    window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        AppKit.NSMakeRect(0, 0, 1280, 840), style, AppKit.NSBackingStoreBuffered, False
    )
    window.setTitle_(_APP_NAME)
    window.setMinSize_(Foundation.NSMakeSize(900, 600))
    _apply_icon(window)

    # One data store shared by both views, so the dashboard and the Blackboard
    # session see each other's cookies exactly as WebView2's shared user-data
    # folder made them share. Non-persistent: nothing is written under
    # ~/Library, so host/_cookies.py owns the saved session instead.
    store = WebKit.WKWebsiteDataStore.nonPersistentDataStore()
    _state["store"] = store

    page = _make_view(AppKit.NSMakeRect(0, 0, 1280, 840), bridged=True, tag="page", store=store)
    window.setContentView_(page)
    window.center()
    window.makeKeyAndOrderFront_(None)
    _state["window"] = window
    _state["page_view"] = page
    _load(url, page)

    # The Blackboard view is never shown. It is given a real window so AppKit
    # lays it out and WebKit will run scripts in it, then parked off screen.
    hidden = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        _TAB_FRAME,
        AppKit.NSWindowStyleMaskBorderless,
        AppKit.NSBackingStoreBuffered,
        False,
    )
    hidden.setReleasedWhenClosed_(False)
    bb = _make_view(_TAB_FRAME, bridged=False, tag="bb", store=store)
    hidden.setContentView_(bb)
    _state["bb_window"] = hidden
    _state["bb_view"] = bb
    _load("about:blank", bb)

    _restore_cookies()


# --------------------------------------------------------------------------
# Document window and its tab strip
# --------------------------------------------------------------------------


def _ensure_doc_window() -> None:
    window = _docs.get("window")
    if window is not None and window.isVisible():
        window.makeKeyAndOrderFront_(None)
        return
    container = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 1100, 760))
    strip = _make_view(
        AppKit.NSMakeRect(0, 760 - _STRIP_HEIGHT, 1100, _STRIP_HEIGHT),
        bridged=True,
        tag="strip",
        store=_state.get("store"),
    )
    strip.setAutoresizingMask_(_MASK_W | _MASK_TOP)
    container.addSubview_(strip)
    _docs["strip_view"] = strip

    window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        AppKit.NSMakeRect(0, 0, 1100, 760),
        AppKit.NSWindowStyleMaskTitled
        | AppKit.NSWindowStyleMaskClosable
        | AppKit.NSWindowStyleMaskMiniaturizable
        | AppKit.NSWindowStyleMaskResizable,
        AppKit.NSBackingStoreBuffered,
        False,
    )
    window.setContentView_(container)
    window.setMinSize_(Foundation.NSMakeSize(520, 320))
    window.center()
    _apply_icon(window)
    _docs["window"] = window
    _docs["container"] = container
    _docs["tabs"] = []
    _docs["active"] = ""
    _docs["next_id"] = 1
    _docs["views"] = {}
    _load(_tabs_url(), strip)
    window.makeKeyAndOrderFront_(None)


def _tabs_url() -> str:
    return (ROOT / "static" / "tabs.html").as_uri()


def _layout_docs() -> None:
    window = _docs.get("window")
    container = _docs.get("container")
    if window is None or container is None:
        return
    bounds = container.bounds()
    width = bounds.size.width
    height = bounds.size.height
    strip = _docs.get("strip_view")
    if strip is not None:
        strip.setFrame_(Foundation.NSMakeRect(0, height - _STRIP_HEIGHT, width, _STRIP_HEIGHT))
    active = str(_docs.get("active") or "")
    views = _docs.get("views") or {}
    for tab in list(_docs.get("tabs") or []):
        view = views.get(tab.get("id"))
        if view is None:
            continue
        shown = tab.get("id") == active
        view.setHidden_(not shown)
        if shown:
            view.setFrame_(Foundation.NSMakeRect(0, 0, width, max(1, height - _STRIP_HEIGHT)))


def _make_tab_view(tab_id: str, url: str) -> None:
    container = _docs.get("container")
    if container is None:
        return
    bounds = container.bounds()
    width = bounds.size.width
    height = max(1, bounds.size.height - _STRIP_HEIGHT)
    view = _make_view(
        Foundation.NSMakeRect(0, 0, width, height),
        bridged=False,
        tag="tab",
        store=_state.get("store"),
    )
    view.setAutoresizingMask_(_MASK_W | _MASK_H | _MASK_TOP)
    # Keep the Python reference before touching AppKit. The view is created
    # autoreleased, and _make_view hands back a borrowed reference; if it is
    # dropped before addSubview_ retains it, the view is freed underneath us and
    # the call never returns.
    (_docs["views"])[tab_id] = view
    container.addSubview_(view)
    _load(url, view)


def _publish_tabs() -> None:
    strip = _docs.get("strip_view")
    if strip is None:
        return
    payload = {
        "event": "tabs",
        "tabs": [
            {
                "id": tab.get("id"),
                "title": tab.get("title") or "Blackboard",
                "active": tab.get("id") == _docs.get("active"),
            }
            for tab in list(_docs.get("tabs") or [])
        ],
    }
    script = "window.__wbDeliver && window.__wbDeliver(%s);" % json.dumps(json.dumps(payload))
    strip.evaluateJavaScript_completionHandler_(script, lambda _v, _e: None)


def _handle_tab_action(message: dict) -> None:
    action = str(message.get("action") or "")
    tab_id = str(message.get("id") or "")
    if action == "ready":
        _publish_tabs()
        _layout_docs()
        return
    tabs = list(_docs.get("tabs") or [])
    chosen = next((tab for tab in tabs if str(tab.get("id")) == tab_id), None)
    if action == "activate" and chosen is not None:
        _docs["active"] = tab_id
        window = _docs.get("window")
        if window is not None:
            window.setTitle_(str(chosen.get("title") or _APP_NAME))
        _layout_docs()
        _publish_tabs()
        return
    if action == "close" and chosen is not None:
        _close_tab(tab_id)


def _close_tab(tab_id: str) -> None:
    tabs = [tab for tab in list(_docs.get("tabs") or []) if str(tab.get("id")) != tab_id]
    views = _docs.get("views") or {}
    view = views.pop(tab_id, None)
    if view is not None:
        try:
            view.stopLoading_(None)
        except Exception:
            pass
        view.removeFromSuperview()
    _docs["tabs"] = tabs
    if not tabs:
        window = _docs.get("window")
        if window is not None:
            window.close()
        _docs["window"] = None
        _docs["container"] = None
        _docs["strip_view"] = None
        return
    if _docs.get("active") == tab_id:
        _docs["active"] = tabs[-1].get("id")
    _layout_docs()
    _publish_tabs()


# --------------------------------------------------------------------------
# Session cookies
# --------------------------------------------------------------------------
#
# WebKit will not let the app choose where its data store lives, so the store is
# non-persistent and the cookies are saved here instead, inside the app's own
# data folder. That is the whole reason this backend avoids ~/Library.


def _cookie_store():
    return _state["store"].httpCookieStore()


def _cookie_noop(*_args) -> None:
    """A real completion handler.

    WKHTTPCookieStore's setters take a block, and pyobjc cannot build one from
    None: WebKit calls it and dereferences a null block, which takes the whole
    process down with SIGSEGV at the next launch that has cookies to restore.
    """


def _cookie_problem(reason: str) -> None:
    """Report a cookie failure instead of failing silently.

    A save that quietly does nothing looks exactly like being signed out, and
    there is nothing in the UI to tell the two apart.
    """
    sys.stderr.write("WhiteBoard: session cookies not saved (%s)\n" % reason)
    sys.stderr.flush()


def _cookie_attr(cookie, attr, default=""):
    """Read one cookie property, tolerating a missing one.

    One unreadable attribute must not cost the whole session, so this returns a
    default instead of raising. NSHTTPCookie names its expiry `expiresDate`;
    asking for `expirationDate` raises AttributeError, which aborted the entire
    save and quietly signed the user out on every launch.
    """
    try:
        value = getattr(cookie, attr)()
    except Exception:
        return default
    return default if value is None else value


def _cookie_record(cookie) -> dict:
    return {
        "name": str(_cookie_attr(cookie, "name")),
        "value": str(_cookie_attr(cookie, "value")),
        "domain": str(_cookie_attr(cookie, "domain")),
        "path": str(_cookie_attr(cookie, "path") or "/"),
        "secure": bool(_cookie_attr(cookie, "isSecure", False)),
        "httpOnly": bool(_cookie_attr(cookie, "isHTTPOnly", False)),
        # Epoch seconds, or 0 for a session cookie. Kept numeric so it maps
        # straight back onto an NSDate without a date format.
        "expires": _epoch(_cookie_attr(cookie, "expiresDate")),
    }


def _epoch(date) -> float:
    if date is None:
        return 0.0
    try:
        return float(date.timeIntervalSince1970())
    except Exception:
        return 0.0


def _cookie_from_record(record: dict):
    """Rebuild an NSHTTPCookie from one saved record.

    NSHTTPCookie has no usable properties-dictionary constructor through pyobjc:
    -[NSHTTPCookie initWithProperties:] returns nil for every key combination,
    so +cookieBySettingProperties: is not the answer either. The route that does
    work is to hand a Set-Cookie header to CFNetwork and take what it parses.
    """
    raw = str(record.get("value") or "")
    # Cookie values are opaque, not URL-encoded. Blackboard sets
    # BbClientCalenderTimeZone=Asia/Shanghai, and encoding every value corrupts
    # it. Encode only what would otherwise terminate the header itself.
    value = quote(raw, safe="") if any(ch in raw for ch in ";\r\n,") else raw
    parts = ["%s=%s" % (record["name"], value)]
    expires = float(record.get("expires") or 0.0)
    if expires:
        parts.append("Expires=" + time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(expires)))
    domain = str(record.get("domain") or "").lstrip(".")
    if domain:
        parts.append("Domain=%s" % domain)
    parts.append("Path=%s" % (record.get("path") or "/"))
    if record.get("secure"):
        parts.append("Secure")
    if record.get("httpOnly"):
        parts.append("HttpOnly")
    url = Foundation.NSURL.URLWithString_("https://%s/" % (domain or "localhost"))
    parsed = Foundation.NSHTTPCookie.cookiesWithResponseHeaderFields_forURL_(
        {"Set-Cookie": "; ".join(parts)}, url
    )
    return parsed[0] if parsed else None


def _restore_cookies() -> None:
    import data

    path = data.APP_DIR / "cookies.json"
    if not path.is_file():
        return
    try:
        from secure_storage import load_secret
        records = load_secret(path, [])
    except Exception:
        return
    if not isinstance(records, list) or not records:
        return
    cookies, skipped = [], []
    for record in records:
        if not isinstance(record, dict) or not record.get("name"):
            continue
        try:
            cookie = _cookie_from_record(record)
        except Exception as exc:
            skipped.append("%s: %s" % (record.get("name"), exc))
            continue
        if cookie is None:
            skipped.append("%s: could not be rebuilt" % record.get("name"))
        else:
            cookies.append(cookie)
    if skipped:
        _cookie_problem("could not restore %d cookie(s): %s" % (len(skipped), skipped[0]))
    if cookies:
        _cookie_store().setCookies_completionHandler_(cookies, _cookie_noop)


def save_cookies() -> None:
    """Write the live Blackboard session next to the rest of the app's data.

    Called after sign-in finishes, and again whenever the app is about to quit.
    Best effort: a failure here costs one extra sign-in, nothing more.
    """
    import data

    store = _cookie_store()
    holder: dict[str, object] = {}
    done = threading.Event()

    def finished(cookies):
        records, failures = [], []
        for item in cookies or []:
            try:
                records.append(_cookie_record(item))
            except Exception as exc:
                failures.append("%s" % exc)
        holder["records"] = records
        if failures:
            holder.setdefault("error", "skipped %d cookie(s): %s" % (len(failures), failures[0]))
        done.set()

    def go():
        try:
            store.getAllCookies_(finished)
        except Exception as exc:
            holder["error"] = str(exc)
            done.set()

    _on_main(go)
    if not done.wait(10):
        _cookie_problem("the cookie store did not answer within 10s")
        return
    if holder.get("error"):
        _cookie_problem(holder["error"])
        return
    records = holder.get("records")
    if not isinstance(records, list):
        _cookie_problem("no cookies came back")
        return
    try:
        data.DATA_DIR.mkdir(parents=True, exist_ok=True)
        from secure_storage import save_secret
        save_secret(data.APP_DIR / "cookies.json", records)
    except Exception as exc:
        _cookie_problem("could not write cookies.json: %s" % exc)


def clear_cookies() -> None:
    """Forget the saved Blackboard session so the next launch asks again."""
    import data

    try:
        from secure_storage import delete_secret
        delete_secret(data.APP_DIR / "cookies.json")
    except FileNotFoundError:
        pass
    except Exception:
        pass
    _on_main(lambda: [_close_tab(str(tab["id"])) for tab in list(_docs.get("tabs") or [])])
    store = _cookie_store()
    holder: list = []
    done = threading.Event()

    def finished(cookies):
        holder.extend(cookies or [])
        done.set()

    _on_main(lambda: store.getAllCookies_(finished))
    if not done.wait(10):
        return
    for cookie in holder:
        try:
            store.deleteCookie_completionHandler_(cookie, _cookie_noop)
        except Exception:
            continue


def show_login():
    def show():
        window = _state["bb_window"]
        window.setStyleMask_(AppKit.NSWindowStyleMaskTitled)
        window.setFrame_display_(AppKit.NSMakeRect(100, 100, 1100, 800), True)
        window.center()
        window.makeKeyAndOrderFront_(None)
    _on_main(show)


def hide_login():
    _on_main(lambda: _state["bb_window"].orderOut_(None))
