# Installation

Full command-level detail lives in the repository [README](https://github.com/LapisLa2uli/WhiteBoard/blob/master/README.md). This page is the wiki summary.

## Packaged app (distribution)

Download from [Releases](https://github.com/LapisLa2uli/WhiteBoard/releases).

| File | Machine |
|---|---|
| `WhiteBoard-<version>-Setup.exe` | Windows 10/11, 64-bit |
| `WhiteBoard-<version>-macOS-Intel.dmg` | Intel Mac |
| `WhiteBoard-<version>-macOS-AppleSilicon.dmg` | Apple Silicon (M1–M4) |
| Source code zip / tar | Development only |

You also need **Google Chrome** or **Microsoft Edge**. WhiteBoard uses one of them to talk to Blackboard.

### Windows

1. Run the setup exe (no administrator account required).
2. Install location: `%LOCALAPPDATA%\Programs\WhiteBoard`.
3. The installer creates a Start menu shortcut named **WhiteBoard** (Windows Search) and optionally a Desktop shortcut with the same name.
4. To **upgrade**, run a newer setup. It replaces the same folder and keeps those shortcut names.

Uninstall from Windows Settings → Apps.

### macOS

1. Open the **Intel** or **Apple Silicon** `.dmg` that matches **About This Mac**.
2. Drag WhiteBoard into Applications.
3. If macOS blocks the app, Control-click WhiteBoard → **Open**.

An Intel Mac cannot run the Apple Silicon disk image.

### First sign-in

School URL, username, password → **Sign in**. See [User Guide](User-Guide.md).

## Development (source)

1. Clone or unzip the source.
2. Python **3.10+**, then a virtualenv.
3. `pip install -r requirements.txt`
4. `python -m playwright install chromium`
5. `python -m app` (or `python run_whiteboard.py`)

Tests: `python -m unittest test_smoke.py`.

See the README for PowerShell vs macOS activate commands, packaging scripts, and where settings are stored (`~/.blackboard_dashboard/`).
