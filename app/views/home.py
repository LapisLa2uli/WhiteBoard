from __future__ import annotations

import flet as ft

from blackboard.api import deadline_is_finished, recent_grades, upcoming

from app.controller import AppController
from app.widgets import (
    assignment_card,
    card,
    deadline_legend,
    empty_state,
    error_banner,
    format_dt,
    heading,
    muted,
    page_scroll,
    section_title,
    status_chip,
)


def build_home(ctrl: AppController) -> ft.Control:
    snapshot = ctrl.store.snapshot
    blocks: list[ft.Control] = [heading("Home"), muted("This week at a glance.")]

    for key, label in (
        ("harvest", "Could not read Ultra pages"),
        ("profile", "Could not load your profile"),
        ("calendar", "Couldn't load deadlines"),
        ("grades", "Couldn't load grades"),
        ("courses", "Couldn't load courses"),
        ("refresh", "Refresh failed"),
    ):
        if snapshot.errors.get(key):
            blocks.append(error_banner(f"{label}: {snapshot.errors[key]}"))

    due = [
        item
        for item in upcoming(snapshot, 7)
        if ctrl.assignment_in_active_filter(item.course_id)
        and not deadline_is_finished(snapshot, item)
    ]
    blocks.append(section_title("Upcoming this week"))
    if due:
        blocks.append(deadline_legend())
        rows = []
        for item in due:
            assignment_id = item.assignment_id or (item.id if item.kind == "assignment" else "")
            course = snapshot.course_name(item.course_id)

            def open_item(e, aid=assignment_id, cid=item.course_id):
                if aid and snapshot.assignment_by_id(aid):
                    ctrl.go(f"/assignments/{aid}", push=True)
                elif cid:
                    ctrl.go(f"/courses/{cid}", push=True)

            rows.append(
                assignment_card(
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(item.title, weight=ft.FontWeight.W_600),
                                    muted(f"{format_dt(item.when)}  ·  {course or 'Course'}"),
                                ],
                                spacing=4,
                                expand=True,
                            ),
                            ft.Column(
                                [
                                    ctrl.countdown_control(
                                        item.when,
                                        status=ctrl.countdown_status(
                                            assignment_id=assignment_id,
                                            kind=item.kind,
                                            title=item.title,
                                            course_id=item.course_id,
                                        ),
                                    ),
                                    status_chip(item.kind),
                                ],
                                spacing=4,
                                horizontal_alignment=ft.CrossAxisAlignment.END,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    course_id=item.course_id,
                    due_at=item.when,
                    on_click=open_item,
                    on_double_tap=lambda e, deadline=item: ctrl.open_work_in_blackboard(
                        url=deadline.blackboard_url,
                        course_id=deadline.course_id,
                        assignment_id=deadline.assignment_id or deadline.id,
                    ),
                )
            )
        blocks.extend(rows)
    else:
        blocks.append(empty_state("No deadlines this week.", ctrl.refresh))

    blocks.append(section_title("Recent grades"))
    grades = [
        grade
        for grade in recent_grades(snapshot, 8)
        if ctrl.assignment_in_active_filter(grade.course_id)
    ][:5]
    if grades:
        for grade in grades:
            course = snapshot.course_name(grade.course_id)

            def open_grade(e, gid=grade.id, cid=grade.course_id, aid=grade.assignment_id):
                if aid and snapshot.assignment_by_id(aid):
                    ctrl.go(f"/assignments/{aid}", push=True)
                elif cid:
                    ctrl.go(f"/courses/{cid}", push=True)

            blocks.append(
                card(
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(grade.title, weight=ft.FontWeight.W_600),
                                    muted(course or "Course"),
                                ],
                                spacing=4,
                                expand=True,
                            ),
                            ft.Text(grade.score or "—", weight=ft.FontWeight.W_600),
                        ]
                    ),
                    on_click=open_grade,
                )
            )
    else:
        blocks.append(empty_state("No new grades.", ctrl.refresh))

    return page_scroll(blocks)
