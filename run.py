"""Start the WhiteBoard window. No network port and no console server."""

from __future__ import annotations

import sys

import data

data.install()

from host import open_window, set_bridge
from server import handle
from shortcuts import install_shortcuts

PAGE = data.resource_root() / "static" / "index.html"


def _check_document_tabs(failures: list[str]) -> None:
    """Open, switch and close document tabs, all called from a worker thread.

    This is the path that traps if any of it runs off the main thread: creating
    a WKWebView (crash in -[WKWebView initWithFrame:configuration:]) and
    closing a window (crash in -[NSWindow _close], which AppKit answers with
    "Must only be used from the main thread"). Both are real AppKit requirements
    rather than anything pyobjc can police, so the only way to know they are
    safe is to drive them the way the app does and see the process survive.
    """
    import time

    import host
    import host._macos as backend

    def check(name: str, cond: bool, detail: str = "") -> None:
        print("%-28s %-18s %s" % (name, "ok" if cond else "FAIL", detail), flush=True)
        if not cond:
            failures.append(name)

    host.open_document("about:blank", "One")
    host.open_document("about:blank", "Two")
    deadline = time.time() + 15
    while time.time() < deadline:
        if len(backend._docs.get("views") or {}) >= 2:
            break
        time.sleep(0.1)
    tabs = backend._docs.get("tabs") or []
    views = backend._docs.get("views") or {}
    check("tabs opened", len(tabs) == 2, "tabs=%d" % len(tabs))
    check("each tab has a view", len(views) == 2, "views=%d" % len(views))
    check("tab views are distinct", len({id(v) for v in views.values()}) == 2)
    check("document window exists", backend._docs.get("window") is not None)

    # Switching the active tab only hides and shows, but it walks the subviews,
    # so it is cheap insurance that the container hierarchy is intact.
    backend._on_main(lambda: backend._handle_tab_action({"action": "activate", "id": "1"}))
    check("active tab switched", backend._docs.get("active") == "1")

    # Closing the last tab closes the window, which is the -[NSWindow _close]
    # trap. Hop to the main thread exactly as the tab strip does.
    backend._on_main(lambda: backend._handle_tab_action({"action": "close", "id": "1"}))
    backend._on_main(lambda: backend._handle_tab_action({"action": "close", "id": "2"}))
    deadline = time.time() + 10
    while time.time() < deadline and backend._docs.get("tabs"):
        time.sleep(0.1)
    check("tabs closed", not (backend._docs.get("tabs") or []))
    check("still alive after closing", True)


def _check_cookies(failures: list[str]) -> None:
    """Save, clear and restore the session cookie jar.

    The restore path used to hand WebKit a null completion block, which
    segfaulted the process on the next launch that had cookies to restore.
    Nothing short of actually doing it catches that.
    """
    import json
    import tempfile
    import time
    from pathlib import Path as _Path

    import data
    import host
    import host._macos as backend

    def check(name: str, cond: bool, detail: str = "") -> None:
        print("%-28s %-18s %s" % (name, "ok" if cond else "FAIL", detail), flush=True)
        if not cond:
            failures.append(name)

    real = data.DATA_DIR
    scratch = _Path(tempfile.mkdtemp(prefix="wb-selftest"))
    try:
        data.DATA_DIR = scratch
        backend._restore_cookies()          # no file yet: must be a clean no-op
        host.save_cookies()
        saved = scratch / "cookies.json"
        check("cookie save wrote a file", saved.is_file())
        if saved.is_file():
            records = json.loads(saved.read_text("utf-8"))
            check("cookie records readable", isinstance(records, list), "n=%d" % len(records))

        host.clear_cookies()
        check("cookies cleared", not saved.is_file())

        # Rebuild one and push it back through the restore path.
        backend._cookie_store().setCookies_completionHandler_(
            [backend._cookie_from_record(
                {"name": "wbtest", "value": "1", "domain": "example.com",
                 "path": "/", "secure": False, "httpOnly": False, "expires": 0})],
            backend._cookie_noop,
        )
        deadline = time.time() + 15
        got = None
        import Foundation

        while time.time() < deadline:
            holder, done = {}, []

            def readback(cookies, _h=holder, _d=done):
                # pyobjc requires a void return from a completion handler.
                _h["names"] = [c.name() for c in (cookies or [])]
                _d.append(1)

            backend._on_main(
                lambda: backend._state["store"].httpCookieStore().getAllCookies_(readback)
            )
            for _ in range(200):
                if done:
                    break
                Foundation.NSRunLoop.currentRunLoop().runMode_beforeDate_(
                    Foundation.NSDefaultRunLoopMode,
                    Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.02),
                )
            got = holder.get("names") or []
            if "wbtest" in got:
                break
            time.sleep(0.2)
        check("cookie set with a real handler", "wbtest" in got, "names=%s" % got)
    except Exception as exc:
        failures.append("cookies: %s: %s" % (type(exc).__name__, exc))
    finally:
        data.DATA_DIR = real


def selftest() -> int:
    """Prove the window host actually works, then exit.

    A build can sign, verify, and contain every file it should, and still fail
    at runtime: WKWebView refuses to start without a bundle identity, a pyobjc
    framework can be missing, and evaluateJavaScript hands back Objective-C
    objects that fail every isinstance check downstream. None of that shows up
    in a static check, so packaging runs this and fails the build instead.

    This lives here rather than being passed as -c to the app because
    PyInstaller's bootloader does not run -c; it launches the app regardless,
    which silently turns any such test into "the app started" and nothing more.
    """
    import threading

    if sys.platform == "win32":
        from host.windows_smoke import run
        return run()

    import AppKit
    import Foundation

    import host._macos as backend

    failures: list[str] = []
    # Set by the worker once every check has run. Without this the main thread
    # can come back from app.run() mid-check and report a pass it never earned.
    finished = threading.Event()

    def record(name: str, value: object, want: str) -> None:
        ok = {
            "dict": isinstance(value, dict),
            "list": isinstance(value, list),
            "None": value is None,
            "ok": bool(value),
        }[want]
        print("%-28s %-18s %s" % (name, type(value).__name__, "ok" if ok else "FAIL"), flush=True)
        if not ok:
            failures.append("%s returned %r" % (name, value))

    import time as _time

    deadline = _time.time() + 120

    def worker() -> None:
        # WebKit delivers its callbacks on the main run loop, so this must not
        # block: the main thread is inside NSApplication below, running it.
        # Everything here also runs off the main thread on purpose, because
        # that is how the real app calls in: crawl.py's worker thread, and the
        # page's bridge messages.
        try:
            backend.wait_browser(timeout=25)
            record("script result", backend.eval_js("1+1", timeout=15), "ok")
            record("object result", backend.eval_js("({a:1})", timeout=15), "dict")
            record("array result", backend.eval_js("([1,2])", timeout=15), "list")
            record("null result", backend.eval_js("(null)", timeout=15), "None")
            icon = backend._app_icon()
            print("%-28s %-18s %s" % ("app icon", type(icon).__name__, "ok" if icon else "FAIL"), flush=True)
            if not icon:
                failures.append("the app icon did not load")
            _check_document_tabs(failures)
            _check_cookies(failures)
        except Exception as exc:
            failures.append("%s: %s" % (type(exc).__name__, exc))
        finally:
            finished.set()

    bundle = Foundation.NSBundle.mainBundle().bundleIdentifier()
    print("bundle identity       %-18s %s" % (str(bundle), "ok" if bundle else "FAIL"), flush=True)
    if not bundle:
        failures.append("no bundle identity, so WKWebView cannot start")
        return 1

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    backend.set_bridge(lambda path, body: {})
    backend._state["page_ready"] = threading.Event()
    backend._state["bb_ready"] = threading.Event()
    backend._state["url"] = "about:blank"
    backend._build("about:blank")

    # Spin the run loop here rather than call app.run(). WebKit delivers its
    # callbacks on this thread, so it has to keep turning while the worker
    # works -- but app.run() only returns once the app terminates, and having
    # the worker terminate it races the results being printed. Polling keeps
    # ownership of the exit here.
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    while not finished.is_set() and _time.time() < deadline:
        Foundation.NSRunLoop.currentRunLoop().runMode_beforeDate_(
            Foundation.NSDefaultRunLoopMode,
            Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.02),
        )
    if not finished.is_set():
        failures.append("the checks did not finish within 120s")
    _time.sleep(0.3)  # let any trailing print land

    if failures:
        print("\nFAILED:", flush=True)
        for line in failures:
            print("  " + line, flush=True)
        return 1
    print("\nself test passed", flush=True)
    return 0


def main() -> None:
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    install_shortcuts()
    set_bridge(handle)
    open_window(PAGE.as_uri())


if __name__ == "__main__":
    main()