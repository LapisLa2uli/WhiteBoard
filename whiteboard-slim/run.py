"""Start the slim WhiteBoard UI in Edge, with no Flet or Playwright."""

from __future__ import annotations

import subprocess
import threading
import time
import webbrowser
from pathlib import Path

from server import serve

PORT = 18765
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def main() -> None:
    threading.Thread(target=lambda: serve(PORT), daemon=True).start()
    time.sleep(0.3)
    url = f"http://127.0.0.1:{PORT}"
    if EDGE.is_file():
        subprocess.Popen([str(EDGE), f"--app={url}", "--new-window"])
    else:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
