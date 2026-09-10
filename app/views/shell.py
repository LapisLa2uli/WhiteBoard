from __future__ import annotations

import flet as ft

from app import theme
from app.branding import logo_image
from app.controller import AppController
from app.navigation import SIDEBAR_ITEMS, top_level_of
from app.views.assignment_detail import build_assignment_detail
from app.views.assignments import build_assignments, build_ignored, build_submitted
from app.views.calendar_view import build_calendar
from app.views.course_detail import build_course_detail
from app.views.courses import build_courses
from app.views.course_sidebar import build_course_sidebar
from app.views.contents import build_contents
from app.views.grades import build_grades
from app.views.home import build_home
from app.views.settings import build_settings
from app.widgets import error_banner, format_refreshed, muted


def build_shell(ctrl: AppController) -> ft.Control:
    snapshot = ctrl.store.snapshot
    current = top_level_of(ctrl.route)

    nav_buttons = []
    for route, label, icon in SIDEBAR_ITEMS:
        selected = current == route
        nav_buttons.append(
            ft.TextButton(
                content=ft.Row(
                    [
                        ft.Icon(icon, size=16, color=theme.ACCENT if selected else theme.MUTED),
                        ft.Text(
                            label,
                            size=13,
                            weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_400,
                            color=theme.ACCENT if selected else theme.TEXT,
                        ),
                    ],
                    spacing=6,
                ),
                on_click=lambda e, dest=route: ctrl.go(dest),
            )
        )

    top = ft.Container(
        bgcolor=theme.CARD_BG,
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border=ft.Border.only(bottom=ft.BorderSide(1, theme.BORDER)),
        content=ft.Row(
            [
                logo_image(width=28, height=28),
                *nav_buttons,
                ft.Container(expand=True),
                muted(format_refreshed(snapshot.fetched_at)),
                ft.Text(snapshot.user_name or "", color=theme.MUTED, size=13),
                ft.OutlinedButton(
                    "Refresh",
                    on_click=lambda e: ctrl.refresh(),
                    disabled=ctrl.busy,
                ),
                ft.TextButton("Log out", on_click=lambda e: ctrl.logout()),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        ),
    )

    banners: list[ft.Control] = []
    if ctrl.busy:
        banners.append(ft.ProgressBar(color=theme.ACCENT, bgcolor=theme.BORDER))
    if snapshot.errors.get("refresh"):
        banners.append(
            ft.Container(
                content=error_banner(f"Refresh failed: {snapshot.errors['refresh']}"),
                padding=ft.Padding.only(left=24, right=24, top=12),
            )
        )

    return ft.Row(
        [
            build_course_sidebar(ctrl),
            ft.Column(
                [top, *banners, ft.Container(content=content_for(ctrl), expand=True)],
                expand=True,
                spacing=0,
            ),
        ],
        expand=True,
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
    )


def content_for(ctrl: AppController) -> ft.Control:
    route = ctrl.route
    if route == "/home":
        return build_home(ctrl)
    if route == "/courses":
        return build_courses(ctrl)
    if route.startswith("/courses/"):
        return build_course_detail(ctrl, route[len("/courses/") :])
    if route == "/assignments":
        return build_assignments(ctrl)
    if route.startswith("/assignments/"):
        return build_assignment_detail(ctrl, route[len("/assignments/") :])
    if route == "/submitted":
        return build_submitted(ctrl)
    if route == "/ignored":
        return build_ignored(ctrl)
    if route == "/grades":
        return build_grades(ctrl)
    if route == "/contents":
        try:
            return build_contents(ctrl)
        except Exception as exc:
            from app.widgets import heading, page_scroll

            return page_scroll(
                [
                    heading("Contents"),
                    error_banner(f"Couldn't open Contents: {exc}"),
                ]
            )
    if route == "/calendar":
        return build_calendar(ctrl)
    if route == "/settings":
        return build_settings(ctrl)
    return build_home(ctrl)
