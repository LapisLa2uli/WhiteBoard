"""Create Desktop and search-index shortcuts for packaged WhiteBoard builds."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.branding import APP_NAME, asset_path, project_root, window_icon_path


def is_packaged() -> bool:
    if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"):
        return True
    if os.environ.get("FLET_APP_PACKAGED") == "1":
        return True
    bundle = macos_app_bundle()
    return bundle is not None


def macos_app_bundle() -> Path | None:
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.name == f"{APP_NAME}.app":
            return parent
    return None


def launch_target() -> tuple[Path, str, Path]:
    """Return (executable, extra arguments, working directory)."""
    if is_packaged():
        bundle = macos_app_bundle()
        if bundle is not None:
            return bundle, "", bundle
        exe = Path(sys.executable).resolve()
        return exe, "", exe.parent
    root = Path(__file__).resolve().parent.parent
    return Path(sys.executable).resolve(), "-m app", root


def shortcut_labels() -> tuple[str, str]:
    if sys.platform == "darwin":
        return "Desktop shortcut", "Applications folder (Spotlight search)"
    return "Desktop shortcut", "Start menu (Windows Search)"


def install_shortcuts(*, desktop: bool = True, search: bool = True) -> str:
    if sys.platform == "darwin":
        return _install_macos(desktop=desktop, search=search)
    if sys.platform.startswith("win"):
        return _install_windows(desktop=desktop, search=search)
    raise RuntimeError("Shortcuts are only created on Windows and macOS.")


def _install_windows(*, desktop: bool, search: bool) -> str:
    target, args, workdir = launch_target()
    icon = window_icon_path() or str(target)
    created: list[str] = []
    if desktop:
        dest = Path.home() / "Desktop" / f"{APP_NAME}.lnk"
        _write_windows_shortcut(dest, target, args, workdir, icon)
        created.append("Desktop")
    if search:
        start_menu = (
            Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
        )
        dest = start_menu / f"{APP_NAME}.lnk"
        _write_windows_shortcut(dest, target, args, workdir, icon)
        created.append("Start menu / Windows Search")
    if not created:
        return "No shortcut locations were selected."
    return "Added " + " and ".join(created) + " shortcuts."


def _write_windows_shortcut(
    link_path: Path,
    target: Path,
    args: str,
    workdir: Path,
    icon: str,
) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "$ws = New-Object -ComObject WScript.Shell\n"
        f"$s = $ws.CreateShortcut({_ps_quote(str(link_path))})\n"
        f"$s.TargetPath = {_ps_quote(str(target))}\n"
        f"$s.Arguments = {_ps_quote(args)}\n"
        f"$s.WorkingDirectory = {_ps_quote(str(workdir))}\n"
        f"$s.IconLocation = {_ps_quote(f'{icon},0')}\n"
        f"$s.Description = {_ps_quote(APP_NAME)}\n"
        "$s.Save()\n"
    )
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "PowerShell shortcut creation failed.").strip()
        raise RuntimeError(err)


def _install_macos(*, desktop: bool, search: bool) -> str:
    created: list[str] = []
    bundle = macos_app_bundle()
    if desktop:
        _macos_desktop_alias(bundle)
        created.append("Desktop")
    if search:
        _macos_applications_entry(bundle)
        created.append("Applications / Spotlight")
    if not created:
        return "No shortcut locations were selected."
    return "Added " + " and ".join(created) + " shortcuts."


def _macos_desktop_alias(bundle: Path | None) -> None:
    desktop = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    if bundle is not None:
        dest = desktop / f"{APP_NAME}.app"
        _replace_path(dest)
        try:
            dest.symlink_to(bundle, target_is_directory=True)
            return
        except OSError:
            pass
        script = (
            f'tell application "Finder" to make alias file to '
            f'POSIX file {_osa_quote(str(bundle))} at POSIX file {_osa_quote(str(desktop))}'
        )
        result = subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "Could not create Desktop alias.").strip())
        return
    _write_macos_launcher(desktop / f"{APP_NAME}.command")


def _macos_applications_entry(bundle: Path | None) -> None:
    apps = Path.home() / "Applications"
    apps.mkdir(parents=True, exist_ok=True)
    dest = apps / f"{APP_NAME}.app"
    if bundle is None:
        raise RuntimeError(
            "WhiteBoard.app was not found. Build the macOS distribution, then try again."
        )
    _replace_path(dest)
    try:
        dest.symlink_to(bundle, target_is_directory=True)
    except OSError:
        shutil.copytree(bundle, dest)


def _write_macos_launcher(path: Path) -> None:
    root = project_root()
    python = Path(sys.executable).resolve()
    path.write_text(
        "#!/bin/bash\n"
        f"cd {_sh_quote(str(root))}\n"
        f"exec {_sh_quote(str(python))} -m app \"$@\"\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | 0o111)


def _replace_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _osa_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def icon_for_bundle() -> Path:
    ico = asset_path("logo.ico")
    if ico.exists():
        return ico
    return asset_path("logo.png")
