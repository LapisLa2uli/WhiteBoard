"""Exercise actual WebView2 startup and the native bridge, in a disposable profile."""
import json
import tempfile
import threading
import time
from pathlib import Path


def run():
    import data
    from host import _windows as backend

    failures = []
    complete = threading.Event()
    bridge_seen = threading.Event()
    profile = tempfile.TemporaryDirectory(prefix="whiteboard-smoke-")
    data.WEBVIEW_PATH = Path(profile.name) / "webview"

    def bridge(path, body):
        if path == "/smoke":
            bridge_seen.set()
        return {"ok": True}

    def worker():
        try:
            backend.wait_browser(30)
            backend.navigate_bb("about:blank")
            deadline = time.monotonic() + 10
            answer = None
            while time.monotonic() < deadline:
                answer = backend.eval_js("({answer:42})")
                if answer == {"answer": 42}:
                    break
                time.sleep(.1)
            assert answer == {"answer": 42}, f"script response: {answer!r}"
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                if backend.eval_page("document.readyState") == "complete":
                    break
                time.sleep(.1)
            backend.eval_page('window.chrome.webview.postMessage(JSON.stringify({id:1,path:"/smoke"}))')
            assert bridge_seen.wait(10), "native bridge did not receive a message"
            backend.open_document("about:blank", "Smoke test")
            deadline = time.monotonic() + 10
            while not backend._docs.get("tabs") and time.monotonic() < deadline:
                time.sleep(.1)
            assert backend._docs.get("tabs"), "document tab did not open"
        except Exception as exc:
            failures.append(str(exc) or type(exc).__name__)
        finally:
            complete.set()
            backend._queue_call(lambda: backend.user32.PostMessageW(backend._state["hwnd"], backend.WM_CLOSE, 0, 0))

    backend.set_bridge(bridge)
    threading.Thread(target=worker, daemon=True).start()
    backend.open_window((data.resource_root() / "static" / "index.html").as_uri())
    if not complete.is_set():
        failures.append("window exited before checks completed")
    print(json.dumps({"passed": not failures, "failures": failures}), flush=True)
    # WebView2 may hold profile files briefly after the last controller closes.
    try:
        profile.cleanup()
    except OSError:
        pass
    return int(bool(failures))
