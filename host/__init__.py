"""WhiteBoard's native window host.

One platform backend, one surface. Windows drives WebView2 through ctypes in
``host._windows``; macOS drives WebKit through pyobjc in ``host._macos``. Both
expose exactly the names re-exported below, and nothing else imports a backend
directly.

The public surface is intentionally small:

    open_window(url)                 create the window and run until it closes
    set_bridge(fn)                   fn(path, body) -> dict, answers the page
    set_title(text)                  window title, also the progress line
    post_page(text)                  JSON reply pushed back into the page
    eval_js(expr, timeout)           run script in the hidden Blackboard view
    eval_page(expr, timeout)         run script in the visible WhiteBoard view
    navigate_bb(url)                 load a URL in the Blackboard view
    wait_browser(timeout)            block until that view can take script
    open_document(url, title)        open a Blackboard page in a document tab
    return_to_app()                 clear the status title
"""

from __future__ import annotations

import sys

__all__ = [
    "ROOT",
    "ICON_PATH",
    "open_window",
    "set_bridge",
    "set_title",
    "post_page",
    "eval_js",
    "eval_page",
    "navigate_bb",
    "wait_browser",
    "open_document",
    "return_to_app",
    "save_cookies",
    "clear_cookies",
]

if sys.platform == "win32":
    from ._windows import (  # noqa: F401
        ICON_PATH,
        ROOT,
        eval_js,
        eval_page,
        navigate_bb,
        open_document,
        open_window,
        clear_cookies,
        post_page,
        return_to_app,
        save_cookies,
        set_bridge,
        set_title,
        wait_browser,
    )
elif sys.platform == "darwin":
    from ._macos import (  # noqa: F401
        ICON_PATH,
        ROOT,
        eval_js,
        eval_page,
        navigate_bb,
        open_document,
        open_window,
        clear_cookies,
        post_page,
        return_to_app,
        save_cookies,
        set_bridge,
        set_title,
        wait_browser,
    )
else:
    raise RuntimeError(
        f"WhiteBoard's window host supports macOS and Windows, not {sys.platform}."
    )