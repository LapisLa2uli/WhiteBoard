"""Start the WhiteBoard window. No network port and no console server."""

from __future__ import annotations

import data

data.install()

from host import open_window, set_bridge
from server import handle
from shortcuts import install_shortcuts

PAGE = data.resource_root() / "static" / "index.html"


def main() -> None:
    install_shortcuts()
    set_bridge(handle)
    open_window(PAGE.as_uri())


if __name__ == "__main__":
    main()
