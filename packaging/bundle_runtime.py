"""Locate and stage runtime binaries that PyInstaller does not collect by default.

Flet-desktop's wheel has no Flutter client archive. Playwright's wheel has a Node
driver but Chromium lives in a user cache unless it is copied into the bundle.
Both must be inside the onedir tree or a clean machine will download them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(__file__).resolve().parent / ".cache"

FLET_ARCHIVES = ("flet-windows.zip", "flet-macos.tar.gz")
PLAYWRIGHT_DRIVERS = ("node.exe", "node")
CHROMIUM_MARKERS = (
    "chrome.exe",
    "chrome",
    "Chromium.app",
)


def ensure_flet_client_archive() -> Path:
    """Return the platform Flet desktop archive, downloading it when missing."""
    import flet_desktop

    artifact = flet_desktop.get_artifact_filename()
    dest = CACHE / "flet" / flet_desktop.version.version / artifact
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        return dest

    url = os.environ.get(
        "FLET_CLIENT_URL",
        f"https://github.com/flet-dev/flet/releases/download/v{flet_desktop.version.version}/{artifact}",
    )
    print(f"Downloading Flet desktop client {artifact} from {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    if tmp.stat().st_size < 1_000_000:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"Flet desktop archive is too small: {tmp}")
    tmp.replace(dest)
    return dest


def playwright_package_browsers() -> Path:
    import playwright

    return (
        Path(playwright.__file__).resolve().parent
        / "driver"
        / "package"
        / ".local-browsers"
    )


def _is_chromium_binary(path: Path) -> bool:
    name = path.name
    if "headless" in path.as_posix().lower():
        return False
    if name in CHROMIUM_MARKERS:
        return path.is_file() or name.endswith(".app")
    return name == "Chromium" and (path.is_file() or path.is_dir())


def _default_playwright_cache() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def _required_browser_dir_names() -> tuple[str, ...]:
    import playwright

    browsers_json = (
        Path(playwright.__file__).resolve().parent / "driver" / "package" / "browsers.json"
    )
    data = json.loads(browsers_json.read_text(encoding="utf-8"))
    names = []
    for item in data.get("browsers", []):
        if item.get("name") in ("chromium", "ffmpeg"):
            names.append(f"{item['name']}-{item['revision']}")
    if not names:
        raise SystemExit("playwright browsers.json did not list chromium/ffmpeg")
    return tuple(names)


def _browser_search_roots() -> tuple[Path, ...]:
    return (
        CACHE / "playwright-browsers",
        playwright_package_browsers(),
        _default_playwright_cache(),
    )


def locate_required_browsers() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for name in _required_browser_dir_names():
        for root in _browser_search_roots():
            candidate = root / name
            if candidate.is_dir():
                found[name] = candidate
                break
    return found


def ensure_playwright_chromium() -> dict[str, Path]:
    """Make sure the Chromium revision Playwright expects is available to copy."""
    found = locate_required_browsers()
    missing = [name for name in _required_browser_dir_names() if name not in found]
    if missing:
        dest = CACHE / "playwright-browsers"
        dest.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(dest)
        print(f"Installing Playwright Chromium into {dest}")
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            env=env,
            check=False,
        )
        found = locate_required_browsers()
    missing = [name for name in _required_browser_dir_names() if name not in found]
    if missing:
        raise SystemExit(
            "Playwright Chromium is not available to bundle. "
            f"Missing folders: {', '.join(missing)}"
        )
    return found


def collect_runtime_datas() -> list[tuple[str, str]]:
    """Extra datas that must appear beside the collected Python packages."""
    archive = ensure_flet_client_archive()
    browsers = ensure_playwright_chromium()
    extras = [(str(archive), "flet_desktop/app")]
    for name, src in browsers.items():
        extras.append((str(src), f"playwright/driver/package/.local-browsers/{name}"))
    return extras


def find_bundle_root(dist_root: Path | None = None) -> Path:
    dist = dist_root or (ROOT / "dist")
    candidates = (
        dist / "WhiteBoard",
        dist / "WhiteBoard.app",
    )
    for path in candidates:
        if path.exists():
            return path
    raise SystemExit(f"No packaged app found under {dist}")


def _find_named(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        hits = sorted(
            path
            for path in root.rglob(name)
            if path.is_file() or name.endswith(".app")
        )
        if hits:
            return hits[0]
    return None


def _local_browser_dirs(bundle: Path) -> list[Path]:
    dirs: list[Path] = []
    for path in bundle.rglob(".local-browsers"):
        if path.is_dir():
            dirs.extend(child for child in path.iterdir() if child.is_dir())
    return dirs


def verify_bundle(dist_root: Path | None = None) -> None:
    """Fail if the packaged tree is missing Flet, Playwright, or Chromium."""
    bundle = find_bundle_root(dist_root)
    archive = _find_named(bundle, FLET_ARCHIVES)
    if archive is None:
        raise SystemExit(
            f"{bundle} is missing the Flet desktop archive "
            f"({', '.join(FLET_ARCHIVES)}). First launch would download it."
        )
    if "flet_desktop" not in archive.as_posix():
        raise SystemExit(f"Flet archive is not under flet_desktop: {archive}")

    unpacked = [
        path
        for path in list(bundle.rglob("flet.exe")) + list(bundle.rglob("Flet.app"))
        if "flet_desktop" in path.as_posix()
    ]
    if unpacked:
        raise SystemExit(
            "Bundle contains an unpacked Flet client in addition to the archive. "
            f"Example: {unpacked[0]}"
        )

    driver = _find_named(bundle, PLAYWRIGHT_DRIVERS)
    if driver is None or "playwright" not in driver.as_posix():
        raise SystemExit(f"{bundle} is missing the Playwright Node driver")

    browser_dirs = _local_browser_dirs(bundle)
    extra = [
        path.name
        for path in browser_dirs
        if "headless" in path.name or not (
            path.name.startswith("chromium-") or path.name.startswith("ffmpeg-")
        )
    ]
    if extra:
        raise SystemExit(
            "Bundle includes unused Playwright browsers "
            f"({', '.join(sorted(extra))}). Only Chromium and FFmpeg should be shipped."
        )
    chromiums = [path.name for path in browser_dirs if path.name.startswith("chromium-")]
    if len(chromiums) > 1:
        raise SystemExit(f"Bundle includes multiple Chromium revisions: {chromiums}")

    chromium = None
    for path in bundle.rglob("*"):
        if ".local-browsers" in path.parts and _is_chromium_binary(path):
            chromium = path
            break
    if chromium is None:
        raise SystemExit(
            f"{bundle} is missing bundled Playwright Chromium. "
            "Install Chromium before packaging."
        )

    print(f"Bundled Flet client: {archive}")
    print(f"Bundled Playwright driver: {driver}")
    print(f"Bundled Chromium: {chromium}")


def prepare() -> None:
    archive = ensure_flet_client_archive()
    browsers = ensure_playwright_chromium()
    print(f"Flet client archive: {archive} ({archive.stat().st_size} bytes)")
    for name, src in browsers.items():
        print(f"Playwright {name}: {src}")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "prepare"
    if command == "verify":
        verify_bundle(Path(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif command == "prepare":
        prepare()
    else:
        raise SystemExit(f"Unknown command {command}. Use prepare or verify.")
