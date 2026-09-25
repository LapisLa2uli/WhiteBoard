from __future__ import annotations

import flet as ft

from app import theme
from app.controller import AppController
from app.paging import PAGE_SIZES
from app.shortcuts import shortcut_labels
from app.widgets import card, format_refreshed, heading, muted, page_scroll


def build_settings(ctrl: AppController) -> ft.Control:
    url_field = ft.TextField(
        label="Blackboard base URL",
        value=ctrl.base_url,
        border_color=theme.BORDER,
        focused_border_color=theme.ACCENT,
        on_blur=lambda e: _save_url(ctrl, url_field.value or ""),
        on_submit=lambda e: _save_url(ctrl, url_field.value or ""),
    )

    return page_scroll(
        [
            heading("Settings"),
            card(
                ft.Column(
                    [
                        url_field,
                        muted(format_refreshed(ctrl.store.snapshot.fetched_at)),
                        ft.Row(
                            [
                                ft.FilledButton(
                                    "Refresh now",
                                    on_click=lambda e: ctrl.refresh(),
                                    disabled=ctrl.busy,
                                    bgcolor=theme.ACCENT,
                                ),
                                ft.OutlinedButton(
                                    "Clear cached snapshot",
                                    on_click=lambda e: ctrl.clear_cache(),
                                ),
                                ft.TextButton("Log out", on_click=lambda e: ctrl.logout()),
                            ],
                            wrap=True,
                        ),
                    ],
                    spacing=12,
                )
            ),
            muted(
                "This app is for your own account only. Course materials stay on Blackboard; "
                "do not republish them. Session cookies stay in memory and are not saved to disk."
            ),
            heading("Lists", 20),
            card(
                ft.Column(
                    [
                        muted(
                            "How many items to show at once on assignments, grades, "
                            "the calendar, course pages, and Contents."
                        ),
                        ft.Dropdown(
                            label="Items on one page",
                            value=str(ctrl.list_page_size),
                            options=[
                                ft.DropdownOption(key=str(size), text=f"Show {size} at once")
                                for size in PAGE_SIZES
                            ],
                            on_select=lambda e: ctrl.set_list_page_size(e.control.value),
                            width=280,
                            border_color=theme.BORDER,
                        ),
                        ft.Text(
                            "More than 20 items on one page can make the app lag.",
                            size=13,
                            color=theme.WARN if ctrl.list_page_size > 20 else theme.MUTED,
                            weight=ft.FontWeight.W_600
                            if ctrl.list_page_size > 20
                            else ft.FontWeight.W_400,
                        ),
                    ],
                    spacing=12,
                )
            ),
            heading("Shortcuts", 20),
            card(
                ft.Column(
                    [
                        muted(
                            "Create a Desktop shortcut and add WhiteBoard to search "
                            f"({shortcut_labels()[1]}). The Windows installer keeps these "
                            "shortcuts when you upgrade."
                        ),
                        ft.Row(
                            [
                                ft.FilledButton(
                                    "Add shortcuts…",
                                    icon=ft.Icons.ADD,
                                    on_click=lambda e: ctrl.show_shortcut_dialog(),
                                    bgcolor=theme.ACCENT,
                                ),
                            ],
                            wrap=True,
                        ),
                        muted(ctrl.shortcut_status) if ctrl.shortcut_status else ft.Container(height=0),
                    ],
                    spacing=12,
                )
            ),
        ]
    )


def _save_url(ctrl: AppController, value: str) -> None:
    url = value.strip().rstrip("/")
    if url and url != ctrl.base_url:
        ctrl.base_url = url
