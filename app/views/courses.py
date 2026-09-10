from __future__ import annotations

import flet as ft

from app import theme
from app.controller import AppController
from app.widgets import empty_state, error_banner, heading, muted, page_scroll, subject_fill


def build_courses(ctrl: AppController) -> ft.Control:
    snapshot = ctrl.store.snapshot
    query = ctrl.course_query.strip().lower()
    courses = snapshot.courses
    if query:
        courses = [
            c
            for c in courses
            if query in c.name.lower() or query in c.term.lower() or query in c.instructor.lower()
        ]

    search = ft.TextField(
        hint_text="Search courses (press Enter)",
        value=ctrl.course_query,
        prefix_icon=ft.Icons.SEARCH,
        border_color="#e2e8f0",
        on_submit=lambda e: _on_search(ctrl, e.control.value or ""),
    )

    blocks: list[ft.Control] = [heading("Courses"), search]
    if snapshot.errors.get("courses"):
        blocks.append(error_banner("Couldn't load courses. Try Refresh."))

    if not courses:
        blocks.append(empty_state("No courses match your search." if query else "No courses loaded.", ctrl.refresh))
        return page_scroll(blocks)

    for course in courses:
        subtitle = " · ".join(part for part in (course.term, course.instructor) if part)
        blocks.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(course.name, weight=ft.FontWeight.W_600, size=16, color=theme.TEXT),
                        muted(subtitle or "Course"),
                    ],
                    spacing=4,
                ),
                bgcolor=subject_fill(course.id),
                border_radius=12,
                padding=16,
                border=ft.Border.all(1, "#cbd5e1"),
                on_click=lambda e, cid=course.id: ctrl.go(f"/courses/{cid}", push=True),
                ink=True,
            )
        )
    return page_scroll(blocks)


def _on_search(ctrl: AppController, value: str) -> None:
    ctrl.course_query = value
    ctrl.rebuild()
