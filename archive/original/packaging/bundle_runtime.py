"""Locate and stage runtime files that PyInstaller does not collect by default.

Flet-desktop's wheel has no Flutter client archive. Playwright's hook collects
its Node driver; WhiteBoard deliberately uses an installed Edge or Chrome
instead of shipping another browser.
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(__file__).resolve().parent / ".cache"

FLET_ARCHIVES = ("flet-windows.zip", "flet-macos.tar.gz")
PLAYWRIGHT_DRIVERS = ("node.exe", "node")
FORBIDDEN_BROWSER_BUNDLES = (
    "playwright-chromium.tar.gz",
    ".local-browsers",
    "ms-playwright",
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
    tmp = dest.with_name(dest.name + ".part")
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "WhiteBoard-packaging"})
            with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            print(f"Download attempt {attempt + 1} failed: {exc}")
            tmp.unlink(missing_ok=True)
    if last_error is not None:
        raise SystemExit(f"Could not download {artifact}: {last_error}") from last_error
    if tmp.stat().st_size < 1_000_000:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"Flet desktop archive is too small: {tmp}")
    tmp.replace(dest)
    return dest


def demote_nested_runtime_binaries(binaries, datas):
    """Keep nested app bundles as data so macOS codesign does not rewrite them."""
    kept = []
    extra_datas = list(datas)
    for entry in binaries:
        dest = str(entry[0]).replace("\\", "/")
        src = str(entry[1]).replace("\\", "/") if len(entry) > 1 else ""
        haystack = f"{dest} {src}"
        if (
            ".app/" in haystack
            or dest.endswith(".app")
            or "Flet.app" in haystack
        ):
            extra_datas.append((entry[0], entry[1], "DATA"))
        else:
            kept.append(entry)
    return kept, extra_datas


def collect_runtime_datas() -> list[tuple[str, str]]:
    """Extra datas that must appear beside the collected Python packages."""
    archive = ensure_flet_client_archive()
    return [(str(archive), "flet_desktop/app")]


def find_bundle_root(dist_root: Path | None = None) -> Path:
    dist = dist_root or (ROOT / "dist")
    app = dist / "WhiteBoard.app"
    onedir = dist / "WhiteBoard"
    if sys.platform == "darwin" and app.exists():
        return app
    for path in (onedir, app):
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


def verify_bundle(dist_root: Path | None = None) -> None:
    """Fail if required runtimes are missing or a browser was bundled."""
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

    forbidden = [
        path
        for path in bundle.rglob("*")
        if path.name in FORBIDDEN_BROWSER_BUNDLES
        or (
            path.is_dir()
            and path.name.startswith(("chromium-", "ffmpeg-", "firefox-", "webkit-"))
        )
        or path.name in ("Chromium.app", "Google Chrome for Testing.app")
    ]
    if forbidden:
        raise SystemExit(
            "Bundle contains a browser payload even though WhiteBoard uses installed "
            f"Edge or Chrome. Example: {forbidden[0]}"
        )

    print(f"Bundled Flet client: {archive}")
    print(f"Bundled Playwright driver: {driver}")
    print("Bundled browser: none (uses installed Edge or Chrome)")


def prepare() -> None:
    archive = ensure_flet_client_archive()
    print(f"Flet client archive: {archive} ({archive.stat().st_size} bytes)")
    print("Browser payload: none (uses installed Edge or Chrome)")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "prepare"
    if command == "verify":
        verify_bundle(Path(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif command == "prepare":
        prepare()
    else:
        raise SystemExit(f"Unknown command {command}. Use prepare or verify.")
