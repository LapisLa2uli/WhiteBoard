from __future__ import annotations

import flet as ft

from app import theme
from app.controller import AppController
from app.paging import PAGE_SIZES
from app.palette import DEADLINE_ROWS, SWATCHES, deadline_color, normalize_hex
from app.shortcuts import shortcut_labels
from app.widgets import card, format_refreshed, heading, muted, page_scroll, subject_fill, subject_ink


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
            heading("Colors", 20),
            card(
                ft.Column(
                    [
                        muted(
                            "Borders show how close a deadline is. Fills show which course "
                            "an item belongs to."
                        ),
                        *[
                            _deadline_row(ctrl, key, label)
                            for key, label, _color in DEADLINE_ROWS
                        ],
                        ft.TextButton(
                            "Reset deadline colors",
                            on_click=lambda e: ctrl.reset_deadline_colors(),
                        ),
                    ],
                    spacing=10,
                )
            ),
            card(_course_color_block(ctrl)),
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


def _deadline_row(ctrl: AppController, key: str, label: str) -> ft.Control:
    color = deadline_color(key)
    return ft.Row(
        [
            ft.Container(
                width=22,
                height=22,
                border_radius=4,
                bgcolor="white",
                border=ft.Border.all(4, color),
            ),
            ft.Text(label, width=130, color=theme.TEXT),
            muted(color, 12),
            ft.TextButton(
                "Change",
                on_click=lambda e, name=label, current=color, band=key: _open_color_dialog(
                    ctrl,
                    f"{name} color",
                    current,
                    lambda value, chosen=band: ctrl.set_deadline_color(chosen, value),
                ),
            ),
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _course_color_block(ctrl: AppController) -> ft.Control:
    courses = sorted(ctrl.store.snapshot.courses, key=lambda course: course.name.lower())
    custom = dict(ctrl.settings.get("course_colors") or {})
    rows: list[ft.Control] = [
        muted("Pick a color for each course. Courses you leave alone keep an automatic color."),
    ]
    if not courses:
        rows.append(muted("Sign in and refresh to choose course colors."))
    for course in courses:
        ink = subject_ink(course.id)
        chosen = course.id in custom
        actions: list[ft.Control] = [
            ft.TextButton(
                "Change",
                on_click=lambda e, item=course, current=ink: _open_color_dialog(
                    ctrl,
                    item.name,
                    current,
                    lambda value, course_id=item.id: ctrl.set_course_color(course_id, value),
                ),
            )
        ]
        if chosen:
            actions.append(
                ft.TextButton(
                    "Reset",
                    on_click=lambda e, course_id=course.id: ctrl.reset_course_color(course_id),
                )
            )
        rows.append(
            ft.Row(
                [
                    ft.Container(
                        width=22,
                        height=22,
                        border_radius=4,
                        bgcolor=subject_fill(course.id),
                        border=ft.Border.all(3, ink),
                    ),
                    ft.Text(course.name, expand=True, color=theme.TEXT),
                    *actions,
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
    if custom:
        rows.append(
            ft.TextButton("Reset course colors", on_click=lambda e: ctrl.reset_course_colors())
        )
    return ft.Column(rows, spacing=8)


def _open_color_dialog(ctrl: AppController, title: str, current: str, on_pick) -> None:
    field = ft.TextField(
        label="Hex color",
        value=current,
        width=180,
        border_color=theme.BORDER,
        focused_border_color=theme.ACCENT,
    )

    def choose(color: str) -> None:
        parsed = normalize_hex(color)
        if not parsed:
            field.error_text = "Use a color like #1d4ed8"
            try:
                field.update()
            except Exception:
                pass
            return
        ctrl.page.pop_dialog()
        on_pick(parsed)

    swatches = ft.Row(
        [
            ft.Container(
                width=28,
                height=28,
                border_radius=6,
                bgcolor=color,
                border=ft.Border.all(3 if color == current else 1, theme.TEXT if color == current else theme.BORDER),
                ink=True,
                on_click=lambda e, chosen=color: choose(chosen),
                tooltip=color,
            )
            for color in SWATCHES
        ],
        spacing=8,
        wrap=True,
    )
    dialog = ft.AlertDialog(
        title=ft.Text(title),
        content=ft.Container(
            width=420,
            content=ft.Column(
                [
                    muted("Choose a swatch, or type a hex color."),
                    swatches,
                    field,
                ],
                spacing=12,
                tight=True,
            ),
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: ctrl.page.pop_dialog()),
            ft.FilledButton(
                "Use this color",
                bgcolor=theme.ACCENT,
                on_click=lambda e: choose(field.value or ""),
            ),
        ],
    )
    ctrl.page.show_dialog(dialog)
