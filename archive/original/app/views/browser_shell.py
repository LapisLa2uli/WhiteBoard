"""Full-window page viewer with a Chrome-style toolbar."""

from __future__ import annotations

import flet as ft

from app.branding import logo_image
from app.controller import AppController
from app.embedded_browser import TOOLBAR_HEIGHT

_BAR = "#e8eaed"
_ICON = "#3c4043"
_PILL = "#ffffff"


def build_browser_shell(ctrl: AppController) -> ft.Control:
    secure = (ctrl.viewer_url or "").startswith("https://")
    address = ft.TextField(
        value=ctrl.viewer_url,
        border=ft.InputBorder.NONE,
        bgcolor=_PILL,
        color="#202124",
        text_size=14,
        expand=True,
        content_padding=ft.Padding.only(left=2, right=8, top=8, bottom=8),
        on_focus=lambda e: _set_editing(ctrl, True),
        on_blur=lambda e: _set_editing(ctrl, False),
        on_submit=lambda e: ctrl.viewer_navigate(e.control.value or ""),
    )
    ctrl.viewer_address = address
    toolbar = ft.Container(
        height=TOOLBAR_HEIGHT,
        bgcolor=_BAR,
        padding=ft.Padding.symmetric(horizontal=6, vertical=6),
        content=ft.Row(
            [
                _icon_button(ft.Icons.ARROW_BACK, "Back", ctrl.viewer_back),
                _icon_button(ft.Icons.ARROW_FORWARD, "Forward", ctrl.viewer_forward),
                _icon_button(ft.Icons.REFRESH, "Reload", ctrl.viewer_reload),
                ft.Container(
                    expand=True,
                    height=36,
                    bgcolor=_PILL,
                    border_radius=18,
                    padding=ft.Padding.only(left=12, right=4),
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.LOCK if secure else ft.Icons.PUBLIC,
                                size=16,
                                color=_ICON,
                            ),
                            address,
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ),
                _icon_button(
                    ft.Icons.OPEN_IN_NEW,
                    "Open in system browser",
                    ctrl.viewer_open_external,
                ),
                ft.Container(
                    border_radius=18,
                    bgcolor=_PILL,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    ink=True,
                    tooltip="Back to WhiteBoard",
                    on_click=lambda e: ctrl.close_viewer(),
                    content=ft.Row(
                        [
                            logo_image(width=18, height=18),
                            ft.Text(
                                "WhiteBoard",
                                size=13,
                                weight=ft.FontWeight.W_600,
                                color=_ICON,
                            ),
                        ],
                        spacing=6,
                        tight=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ),
            ],
            spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )
    body: ft.Control
    if ctrl.viewer_error:
        body = ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            bgcolor="#ffffff",
            padding=24,
            content=ft.Text(ctrl.viewer_error, size=14, color="#3c4043"),
        )
    else:
        body = ft.Container(expand=True, bgcolor="#ffffff")
    return ft.Column([toolbar, body], expand=True, spacing=0)


def _set_editing(ctrl: AppController, editing: bool) -> None:
    ctrl.viewer_editing = editing


def _icon_button(icon, tip: str, handler) -> ft.Control:
    return ft.IconButton(
        icon=icon,
        icon_size=18,
        icon_color=_ICON,
        tooltip=tip,
        on_click=lambda e: handler(),
        style=ft.ButtonStyle(
            padding=0,
            shape=ft.CircleBorder(),
            overlay_color="#1a000000",
        ),
    )
