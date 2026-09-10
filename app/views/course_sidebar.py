from __future__ import annotations

import flet as ft

from app import theme
from app.branding import logo_image
from app.controller import AppController
from app.filters import INACTIVITY_OPTIONS
from app.widgets import muted, subject_fill, subject_ink


def build_course_sidebar(ctrl: AppController) -> ft.Control:
    search = ft.TextField(
        hint_text="Search courses",
        value=ctrl.course_query,
        prefix_icon=ft.Icons.SEARCH,
        bgcolor="#1e293b",
        color="white",
        border_color="#334155",
        focused_border_color=theme.ACCENT,
        cursor_color="white",
        on_change=lambda e: ctrl.set_course_query(e.control.value or ""),
    )
    inactivity = ft.Dropdown(
        label="Activity",
        label_style=ft.TextStyle(color="#e2e8f0"),
        text_style=ft.TextStyle(color="white"),
        color="white",
        value=ctrl.inactivity,
        options=[
            ft.DropdownOption(key=key, text=label) for key, label in INACTIVITY_OPTIONS
        ],
        on_select=lambda e: ctrl.set_inactivity(e.control.value or "all"),
        filled=True,
        fill_color="#1e293b",
        border_color="#334155",
        focused_border_color=theme.ACCENT,
        trailing_icon=ft.Icon(ft.Icons.ARROW_DROP_DOWN, color="white"),
        width=248,
    )

    chips: list[ft.Control] = []
    active_id = str(ctrl.settings.get("active_custom_filter") or "")
    for item in ctrl.custom_filters:
        selected = item.get("id") == active_id
        chips.append(
            ft.Row(
                [
                    ft.Container(
                        content=ft.Text(str(item.get("name") or "Filter"), size=12, color="white"),
                        bgcolor=theme.SIDEBAR_ACTIVE if selected else "#1e293b",
                        border=ft.Border.all(1, "#334155"),
                        border_radius=999,
                        padding=ft.Padding.only(left=10, right=10, top=6, bottom=6),
                        on_click=lambda e, fid=item.get("id"): ctrl.toggle_custom_filter(str(fid)),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_size=14,
                        icon_color="#cbd5e1",
                        tooltip="Delete filter",
                        on_click=lambda e, fid=item.get("id"): ctrl.confirm_delete_custom_filter(
                            str(fid)
                        ),
                    ),
                ],
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    list_column = ft.Column(
        course_list_controls(ctrl),
        spacing=6,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
    ctrl.course_list_column = list_column

    return ft.Container(
        width=280,
        bgcolor=theme.SIDEBAR_BG,
        padding=12,
        content=ft.Column(
            [
                ft.Row(
                    [
                        logo_image(width=28, height=28),
                        ft.Text("WhiteBoard", color="white", size=16, weight=ft.FontWeight.W_700),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text("Your courses", color="#cbd5e1", size=12, weight=ft.FontWeight.W_600),
                search,
                inactivity,
                ft.Row(
                    [
                        muted("Custom filters", 11),
                        ft.Container(expand=True),
                        ft.TextButton(
                            "New",
                            on_click=lambda e: ctrl.show_new_filter_dialog(),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(chips, wrap=True, spacing=6, run_spacing=6)
                if chips
                else muted("No custom filters yet.", 11),
                ft.Checkbox(
                    label="Hide assignments outside this filter",
                    value=ctrl.hide_filtered_assignments,
                    on_change=lambda e: ctrl.set_hide_filtered_assignments(
                        bool(e.control.value)
                    ),
                    label_style=ft.TextStyle(color="#e2e8f0", size=11),
                    check_color="white",
                    fill_color=theme.ACCENT,
                ),
                ft.Checkbox(
                    label="Next launch, only load this filter",
                    value=bool(ctrl.settings.get("load_filter_courses_only")),
                    on_change=lambda e: ctrl.set_load_filter_courses_only(
                        bool(e.control.value)
                    ),
                    label_style=ft.TextStyle(color="#e2e8f0", size=11),
                    check_color="white",
                    fill_color=theme.ACCENT,
                ),
                list_column,
            ],
            spacing=10,
            expand=True,
        ),
    )


def course_list_controls(ctrl: AppController) -> list[ft.Control]:
    rows = ctrl.listed_courses()
    if not rows:
        message = (
            "No matching courses."
            if ctrl.course_query.strip()
            else "No courses in this filter."
        )
        return [muted(message, 12)]

    controls: list[ft.Control] = []
    for course, hidden in rows:
        subtitle = course.term or "Course"
        labels = [
            ft.Text(course.name, color=theme.TEXT, size=13, weight=ft.FontWeight.W_600),
            ft.Text(subtitle, color=theme.MUTED, size=11),
        ]
        if hidden:
            labels.append(
                ft.Text("Filtered out", color=theme.WARN, size=10, weight=ft.FontWeight.W_600)
            )
        controls.append(
            ft.Container(
                content=ft.Column(labels, spacing=2),
                bgcolor=subject_fill(course.id) if not hidden else "#e2e8f0",
                border=ft.Border.all(1, subject_ink(course.id) if not hidden else "#cbd5e1"),
                border_radius=10,
                padding=10,
                opacity=0.55 if hidden else 1,
                on_click=lambda e, cid=course.id: ctrl.go(f"/courses/{cid}", push=True),
                ink=True,
            )
        )
    return controls
