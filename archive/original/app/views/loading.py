from __future__ import annotations

import flet as ft

from app import theme
from app.branding import logo_image
from app.controller import AppController
from app.widgets import format_loading_message, heading, muted


def build_loading(ctrl: AppController) -> ft.Control:
    percent = max(0, min(100, int(round(ctrl.loading_progress * 100))))
    bar = ft.ProgressBar(
        value=ctrl.loading_progress,
        color=theme.ACCENT,
        bgcolor=theme.BORDER,
        bar_height=8,
        width=416,
    )
    label = ft.Text(
        format_loading_message(ctrl.loading_message or "Loading…"),
        color=theme.TEXT,
        size=14,
        expand=True,
        max_lines=1,
        no_wrap=True,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    percent_label = ft.Text(f"{percent}%", color=theme.MUTED, size=13, no_wrap=True)
    ctrl.loading_bar = bar
    ctrl.loading_label = label
    ctrl.loading_percent = percent_label
    refreshing = ctrl.loading_kind == "refresh"
    return ft.Container(
        expand=True,
        bgcolor=theme.PAGE_BG,
        alignment=ft.Alignment.CENTER,
        content=ft.Container(
            width=480,
            bgcolor=theme.CARD_BG,
            border_radius=16,
            padding=32,
            border=ft.Border.all(1, theme.BORDER),
            content=ft.Column(
                [
                    ft.Row(
                        [logo_image(width=64, height=64)],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    heading(
                        "Refreshing your dashboard"
                        if refreshing
                        else "Loading your dashboard"
                    ),
                    muted(
                        "Signing in and collecting courses, assignment links, "
                        "and submission status."
                        if not refreshing
                        else (
                            "Collecting courses, assignment links, and submission "
                            "status. If the Blackboard session expired, the app "
                            "signs you back in."
                        )
                    ),
                    ft.Column(
                        [
                            ft.Row(
                                [label, percent_label],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=8,
                            ),
                            bar,
                        ],
                        spacing=10,
                    ),
                    ft.TextButton("Cancel", on_click=lambda e: ctrl.cancel_loading()),
                ],
                spacing=18,
                tight=True,
            ),
        ),
    )
