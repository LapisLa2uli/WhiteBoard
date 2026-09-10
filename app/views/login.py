from __future__ import annotations

import flet as ft

from app import theme
from app.branding import logo_image
from app.controller import AppController
from app.widgets import heading, muted


def build_login(ctrl: AppController) -> ft.Control:
    url_field = ft.TextField(
        label="School URL",
        value=ctrl.base_url,
        border_color=theme.BORDER,
        focused_border_color=theme.ACCENT,
        on_submit=lambda e: _submit(ctrl, url_field, user_field, password_field),
    )
    user_field = ft.TextField(
        label="Username",
        value=ctrl.login_username,
        autofocus=not bool(ctrl.login_username),
        border_color=theme.BORDER,
        focused_border_color=theme.ACCENT,
        on_submit=lambda e: _submit(ctrl, url_field, user_field, password_field),
    )
    password_field = ft.TextField(
        label="Password",
        value=ctrl._login_password,
        password=True,
        can_reveal_password=True,
        autofocus=bool(ctrl.login_username),
        border_color=theme.BORDER,
        focused_border_color=theme.ACCENT,
        on_submit=lambda e: _submit(ctrl, url_field, user_field, password_field),
    )
    status_color = {
        "failed": theme.LATE,
        "waiting_sso": theme.WARN,
        "signed_in": theme.OK,
        "opening": theme.ACCENT,
        "loading": theme.ACCENT,
    }.get(ctrl.login_status, theme.MUTED)

    actions = [
        ft.FilledButton(
            "Sign in",
            on_click=lambda e: _submit(ctrl, url_field, user_field, password_field),
            disabled=ctrl.busy,
            bgcolor=theme.ACCENT,
            color="white",
        )
    ]
    if ctrl.busy:
        actions.append(ft.TextButton("Cancel", on_click=lambda e: ctrl.cancel_login()))

    return ft.Container(
        expand=True,
        bgcolor=theme.PAGE_BG,
        alignment=ft.Alignment.CENTER,
        content=ft.Container(
            width=440,
            bgcolor=theme.CARD_BG,
            border_radius=16,
            padding=32,
            border=ft.Border.all(1, theme.BORDER),
            content=ft.Column(
                [
                    ft.Row(
                        [logo_image(width=72, height=72)],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    heading("WhiteBoard"),
                    muted(
                        "Sign in with your Blackboard username and password. "
                        "The password stays in memory only and is never saved."
                    ),
                    url_field,
                    user_field,
                    password_field,
                    ft.Row(actions, spacing=8),
                    ft.Row(
                        [
                            ft.ProgressRing(width=16, height=16, stroke_width=2, color=theme.ACCENT)
                            if ctrl.busy
                            else ft.Container(width=0, height=0),
                            ft.Text(ctrl.login_message, color=status_color, size=13)
                            if ctrl.login_message
                            else ft.Container(height=0),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                    if ctrl.login_message or ctrl.busy
                    else ft.Container(height=0),
                    muted("Personal use only. Follow your school's rules for automated access."),
                ],
                spacing=14,
                tight=True,
            ),
        ),
    )


def _submit(
    ctrl: AppController,
    url_field: ft.TextField,
    user_field: ft.TextField,
    password_field: ft.TextField,
) -> None:
    ctrl.base_url = (url_field.value or ctrl.base_url).strip()
    if not ctrl.base_url:
        ctrl.login_status = "failed"
        ctrl.login_message = "School URL is required."
        ctrl.rebuild()
        return
    ctrl.start_login(user_field.value or "", password_field.value or "")
