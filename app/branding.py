"""Resolve bundled logo files for window chrome and in-app branding."""

from __future__ import annotations

import sys
from pathlib import Path

import flet as ft

APP_NAME = "WhiteBoard"


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundled = Path(meipass)
            if (bundled / "assets").exists():
                return bundled
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "assets").exists():
            return exe_dir
        for parent in Path(sys.executable).resolve().parents:
            if parent.suffix == ".app":
                resources = parent / "Contents" / "Resources"
                if (resources / "assets").exists():
                    return resources
                if (parent / "assets").exists():
                    return parent
        return exe_dir
    return Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "assets")
        exe = Path(sys.executable).resolve()
        candidates.extend(
            [
                exe.parent / "assets",
                exe.parent / "_internal" / "assets",
            ]
        )
        for parent in exe.parents:
            if parent.name == f"{APP_NAME}.app":
                candidates.extend(
                    [
                        parent / "Contents" / "Resources" / "assets",
                        parent / "Contents" / "MacOS" / "assets",
                        parent / "assets",
                    ]
                )
                break
    candidates.append(Path(__file__).resolve().parent.parent / "assets")
    for path in candidates:
        if path.exists():
            return path
    return Path(__file__).resolve().parent.parent / "assets"


def asset_path(name: str) -> Path:
    return assets_dir() / name


def window_icon_path() -> str | None:
    ico = asset_path("logo.ico")
    if ico.exists():
        return str(ico)
    png = asset_path("logo.png")
    if png.exists():
        return str(png)
    return None


def apply_window_icon(page: ft.Page) -> None:
    path = window_icon_path()
    window = getattr(page, "window", None)
    if path and window is not None:
        try:
            window.icon = path
        except Exception:
            pass


def logo_image(*, width: int = 72, height: int = 72) -> ft.Control:
    png = asset_path("logo.png")
    if not png.exists():
        return ft.Container(width=width, height=height)
    return ft.Image(
        src=str(png),
        width=width,
        height=height,
        fit=ft.BoxFit.CONTAIN,
        error_content=ft.Container(width=width, height=height),
    )
