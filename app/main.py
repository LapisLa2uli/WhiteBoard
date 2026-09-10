"""Desktop dashboard for a personal Blackboard session."""

from __future__ import annotations

import argparse
import sys

import flet as ft

from app import theme
from app.branding import apply_window_icon, assets_dir
from app.controller import AppController


def build_app(page: ft.Page, *, demo: bool = False) -> AppController:
    page.title = "WhiteBoard"
    page.padding = 0
    page.bgcolor = theme.PAGE_BG
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=theme.ACCENT)
    _size_window(page)
    apply_window_icon(page)

    ctrl = AppController(page, demo=demo)
    try:
        ctrl.file_picker = ft.FilePicker()
    except Exception:
        ctrl.file_picker = None

    def cleanup(_e=None) -> None:
        ctrl._close_session()

    page.on_disconnect = cleanup
    if demo:
        ctrl.enter_demo()
    else:
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="WhiteBoard desktop dashboard")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Open the signed-in UI with sample data (no login).",
    )
    args, _unknown = parser.parse_known_args(argv)

    ft.app(
        target=lambda page: build_app(page, demo=args.demo),
        assets_dir=str(assets_dir()),
    )


if __name__ == "__main__":
    main(sys.argv[1:])
