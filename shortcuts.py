"""Desktop and Start menu shortcuts so Windows Search can open WhiteBoard Slim."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUN = ROOT / "run.py"
ICON = ROOT.parent / "assets" / "logo.ico"
NAME = "WhiteBoard Slim"


def install_shortcuts() -> None:
    """Point Desktop and Start menu entries at this window. Safe to run again."""
    python = Path(sys.executable)
    if python.name.lower() == "python.exe":
        windowless = python.with_name("pythonw.exe")
        if windowless.is_file():
            python = windowless
    desktop = Path.home() / "Desktop"
    start = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    script = r"""
$shell = New-Object -ComObject WScript.Shell
function Save-Link($folder) {
  if (-not (Test-Path -LiteralPath $folder)) { return }
  $link = $shell.CreateShortcut((Join-Path $folder $env:WB_LINK_NAME))
  $link.TargetPath = $env:WB_PYTHON
  $link.Arguments = '"' + $env:WB_RUN + '"'
  $link.WorkingDirectory = $env:WB_WORKDIR
  $link.WindowStyle = 1
  $link.Description = 'WhiteBoard'
  if (Test-Path -LiteralPath $env:WB_ICON) { $link.IconLocation = $env:WB_ICON + ',0' }
  $link.Save()
}
Save-Link $env:WB_DESKTOP
Save-Link $env:WB_START
"""
    env = {
        "WB_LINK_NAME": f"{NAME}.lnk",
        "WB_PYTHON": str(python),
        "WB_RUN": str(RUN),
        "WB_WORKDIR": str(ROOT),
        "WB_ICON": str(ICON),
        "WB_DESKTOP": str(desktop),
        "WB_START": str(start),
    }
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=False,
            env={**dict(**{k: v for k, v in __import__("os").environ.items()}), **env},
            capture_output=True,
            text=True,
        )
    except Exception:
        return
