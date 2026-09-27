"""Start the slim WhiteBoard window. No network port and no console server."""

from __future__ import annotations

from pathlib import Path

import data

data.install()

from host import open_window, set_bridge
from server import handle
from shortcuts import install_shortcuts

PAGE = Path(__file__).resolve().parent / "static" / "index.html"


def main() -> None:
    install_shortcuts()
    set_bridge(handle)
    open_window(PAGE.as_uri())


if __name__ == "__main__":
    main()
