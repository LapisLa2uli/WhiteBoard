"""Desktop dashboard for a personal Blackboard session."""

from __future__ import annotations

import os
import sys

import flet as ft

from app import theme
from app.branding import apply_window_icon, assets_dir
from app.controller import AppController


def build_app(page: ft.Page) -> AppController:
    page.title = "WhiteBoard"
    page.padding = 0
    page.bgcolor = theme.PAGE_BG
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=theme.ACCENT)
    _size_window(page)
    apply_window_icon(page)

    ctrl = AppController(page)
    try:
        ctrl.file_picker = ft.FilePicker()
    except Exception:
        ctrl.file_picker = None

    def cleanup(_e=None) -> None:
        ctrl._close_session()

    page.on_disconnect = cleanup
    ctrl.rebuild()
    return ctrl


def _size_window(page: ft.Page) -> None:
    window = getattr(page, "window", None)
    if window is None:
        page.window = ft.Window(width=1240, height=780, min_width=980, min_height=620)
        return
    window.width = 1240
    window.height = 780
    window.min_width = 980
    window.min_height = 620


def main(_argv: list[str] | None = None) -> None:
    if getattr(sys, "frozen", False):
        os.environ.setdefault("FLET_APP_PACKAGED", "1")
    ft.app(
        target=build_app,
        assets_dir=str(assets_dir()),
    )


if __name__ == "__main__":
    main(sys.argv[1:])
