# WhiteBoard

WhiteBoard is a personal desktop dashboard for your own Blackboard account. It signs in through Chrome or Edge, loads courses, assignments, grades, calendar items, and course files, and keeps a live countdown on work that is still due.

This README covers **distribution (installer) setup** and **development (source) setup**. For a full map of features, screens, and buttons, see the [wiki](https://github.com/LapisLa2uli/WhiteBoard/wiki) or the copies in [`docs/`](docs/Home.md) ([Features](docs/Features.md), [User Guide](docs/User-Guide.md)).

Current release: **[0.1.3](https://github.com/LapisLa2uli/WhiteBoard/releases/tag/v0.1.3)** · [Changelog](CHANGELOG.md)

---

## What you need

| | Distribution build | Development (source) |
|---|---|---|
| OS | Windows 10/11 (64-bit), or macOS 11+ | Same |
| Python | Not required | **Python 3.10** or newer |
| Browser | Bundled Chromium (Chrome/Edge optional) | Chrome, Edge, or `playwright install chromium` |
| Network | Access to your school's Blackboard site | Same |

The packaged app ships its own Chromium. From source, WhiteBoard prefers an installed **Edge** or **Chrome** copy, or a Playwright Chromium download.

The app is for **your own account only**. Follow your school's rules for automated access. Course materials stay on Blackboard; do not republish them.

---

## Distribution installation

Download installers from [Releases](https://github.com/LapisLa2uli/WhiteBoard/releases). GitHub also attaches a **Source code (zip)** on every release.

Pick the file that matches your machine:

| File | Use this when |
|---|---|
| `WhiteBoard-*-Setup.exe` | Windows 10 or 11, 64-bit |
| `WhiteBoard-*-macOS-Intel.dmg` | Intel Mac (About This Mac shows **Intel**) |
| `WhiteBoard-*-macOS-AppleSilicon.dmg` | Apple Silicon Mac (M1 / M2 / M3 / M4) |
| `Source code (zip)` | You want the source tree, not a packaged app |

Using the Apple Silicon disk image on an Intel Mac produces *“this application is not supported on this Mac.”* Check **Apple menu → About This Mac** if you are unsure.

### Windows

1. Download `WhiteBoard-<version>-Setup.exe` from the latest release.
2. Run the installer. It does **not** need administrator rights.
3. The app installs to `%LOCALAPPDATA%\Programs\WhiteBoard` (typically `C:\Users\<you>\AppData\Local\Programs\WhiteBoard`).
4. Leave **Create a Desktop shortcut** checked if you want a Desktop icon. A Start menu entry named **WhiteBoard** is always created, so Windows Search can find it.
5. Finish the wizard and launch WhiteBoard.

**Upgrade:** run a newer `WhiteBoard-*-Setup.exe` on top of the existing install. The installer replaces files in the same folder and retargets the Desktop and Start menu shortcuts. You do not need to uninstall first.

**Uninstall:** Windows Settings → Apps → WhiteBoard → Uninstall, or use *Uninstall WhiteBoard* from the Start menu.

**First launch (Windows):** Sign in with your school URL, username, and password. Chromium is included in the installer.

### macOS

1. Download the matching `.dmg`:
   - Intel MacBook / iMac → `WhiteBoard-*-macOS-Intel.dmg`
   - M-series Mac → `WhiteBoard-*-macOS-AppleSilicon.dmg`
2. Open the disk image.
3. Drag **WhiteBoard** into **Applications** (the Applications alias is on the disk image).
4. Eject the disk image.
5. Open **WhiteBoard** from Applications, Launchpad, or Spotlight.

**Gatekeeper:** the app is not Apple-notarized. If macOS says it cannot verify the developer:

1. Finder → Applications.
2. **Control-click** (or right-click) **WhiteBoard**.
3. Choose **Open**, then confirm **Open**.

You only need to do that once.

**Shortcuts dialog:** if you did not install via the Windows setup program, the first successful sign-in may ask to add a Desktop shortcut and an Applications / Spotlight entry. Choose **Add shortcuts** or **Not now**. You can create them later from **Settings**.

**Uninstall (macOS):** drag `WhiteBoard.app` from Applications to the Trash. Optional local data is listed under [Data stored on your computer](#data-stored-on-your-computer).

### After install: sign in

1. Enter your **School URL** (example default: `https://shs.blackboardchina.cn`).
2. Enter your Blackboard **Username** and **Password**.
3. Click **Sign in**.

The password is kept **in memory only** for this session so Refresh can re-authenticate if Blackboard times out. It is never written to disk. Username and school URL are remembered.

If sign-in fails, confirm Chrome or Edge is installed, the school URL is correct, and you can reach Blackboard in a normal browser.

---

## Development installation

Use this when you want to run WhiteBoard from source (editing code, running tests, or skipping the installer).

### 1. Get the source

```bash
git clone https://github.com/LapisLa2uli/WhiteBoard.git
cd WhiteBoard
```

Or download **Source code (zip)** from a [release](https://github.com/LapisLa2uli/WhiteBoard/releases) and extract it.

### 2. Python 3.10+

- **Windows:** [python.org](https://www.python.org/downloads/) or `winget install Python.Python.3.10`. During setup, enable **Add python.exe to PATH**.
- **macOS:** python.org installer, Homebrew (`brew install python@3.10`), or pyenv.

Check:

```bash
python --version
```

On some Windows installs the command is `py -3.10` instead of `python`.

### 3. Virtual environment

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If activation is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### 4. Dependencies

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

`requirements.txt` installs **Flet** (the UI) and **Playwright** (the Blackboard session). From source, also download Chromium or keep Chrome/Edge installed. Packaged installers already include both the Flet desktop client and Chromium.

### 5. Run the app

From the repository root, with the venv active:

```bash
python -m app
```

or:

```bash
python run_whiteboard.py
```

A window titled **WhiteBoard** should open at 1240×780. Sign in the same way as the packaged app.

### 6. Tests (optional)

```bash
python -m unittest test_smoke.py
```

These tests do not log into a live Blackboard site.

### 7. CLI snapshot helper (optional)

`blackboard_client.py` opens a visible Blackboard window so you can sign in interactively and dump a JSON snapshot. Use only with your own account:

```bash
python blackboard_client.py --base-url https://your-school.blackboard.com
```

### Dev notes

- Do not commit `credentials.txt`, `.venv/`, `dist/`, `build/`, or `packaging/tools/`. They are gitignored.
- Local settings live in `~/.blackboard_dashboard/` (see below), not in the repo.
- Packaging for a new installer: Windows `packaging/build_windows.ps1`; macOS `packaging/build_macos.sh`. GitHub Actions builds both Mac architectures and the Windows setup when you push a `v*` tag.

---

## Data stored on your computer

| Path | Contents |
|---|---|
| `~/.blackboard_dashboard/settings.json` | School URL, username, filters, ignored and “marked submitted” assignment lists, Contents view mode. **No password.** |
| `~/.blackboard_dashboard/snapshot.json` | Last loaded courses, assignments, grades, calendar, and file metadata cache. |

On Windows, `~` is your user profile (`C:\Users\<you>`).

**Log out** closes the browser session and clears the in-memory password. **Clear cached snapshot** in Settings deletes `snapshot.json` but keeps settings. To wipe everything, delete the `.blackboard_dashboard` folder.

Session cookies stay in memory for the running process and are not saved to disk.

---

## Building installers from source

You only need this if you are producing a release yourself. Bump `APP_VERSION` in `app/branding.py` and add a `## [x.y.z]` section to [`CHANGELOG.md`](CHANGELOG.md) that lists the major changes from the previous release. Packaging and the GitHub release job both require that section.

**Windows** (PyInstaller + Inno Setup; the script downloads Inno Setup into `packaging/tools/` if needed):

```powershell
python -m pip install -r requirements.txt -r packaging/requirements-build.txt
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\packaging\.cache\playwright-browsers"
python -m playwright install chromium
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_windows.ps1
```

Output: `dist/WhiteBoard-Setup.exe`.

**macOS:**

```bash
python3 -m pip install -r requirements.txt -r packaging/requirements-build.txt
export PLAYWRIGHT_BROWSERS_PATH="$PWD/packaging/.cache/playwright-browsers"
python3 -m playwright install chromium
bash packaging/build_macos.sh
```

Output: `dist/WhiteBoard-arm64.dmg` or `dist/WhiteBoard-x86_64.dmg` depending on the Mac you built on. Official releases build **both** on GitHub Actions (`macos-latest` for Apple Silicon, `macos-15-intel` for Intel).

---

## License and use

Personal dashboard for a single Blackboard account. Course content remains on Blackboard. Do not share session data or republish downloaded files.
