from __future__ import annotations

import flet as ft

from blackboard.api import _resolve_assignment_status, deadline_is_finished, upcoming

from app.controller import AppController
from app.widgets import (
    assignment_card,
    card,
    empty_state,
    format_dt,
    heading,
    muted,
    page_scroll,
    section_title,
    status_chip,
)


def build_course_detail(ctrl: AppController, course_id: str) -> ft.Control:
    snapshot = ctrl.store.snapshot
    course = snapshot.course_by_id(course_id)
    if not course:
        return page_scroll(
            [
                ft.TextButton("Back", on_click=lambda e: ctrl.back()),
                heading("Course not found"),
                muted("This course is not in the current snapshot."),
            ]
        )

    work = [a for a in snapshot.assignments if a.course_id == course_id]
    work.sort(key=lambda a: a.due_at.timestamp() if a.due_at else float("inf"))
    grades = [g for g in snapshot.grades if g.course_id == course_id]
    notes = [n for n in snapshot.announcements if n.course_id == course_id]
    due = [
        deadline
        for deadline in upcoming(snapshot, 21)
        if deadline.course_id == course_id and not deadline_is_finished(snapshot, deadline)
    ]

    blocks: list[ft.Control] = [
        ft.TextButton("Back", icon=ft.Icons.ARROW_BACK, on_click=lambda e: ctrl.back()),
        heading(course.name),
        muted(" · ".join(part for part in (course.term, course.instructor) if part) or "Course"),
        section_title("Upcoming work"),
    ]

    upcoming_items = due or [
        assignment
        for assignment in work
        if _resolve_assignment_status(snapshot, assignment) != "submitted"
    ]
    if upcoming_items:
        for item in upcoming_items:
            if hasattr(item, "status"):
                title = item.title
                when = item.due_at
                aid = item.id
                status = ctrl.countdown_status(
                    assignment_id=aid,
                    title=item.title,
                    course_id=course_id,
                    kind=item.status,
                )
                chip = status
            else:
                title = item.title
                when = item.when
                aid = item.assignment_id or item.id
                status = ctrl.countdown_status(
                    assignment_id=aid,
                    kind=getattr(item, "kind", ""),
                    title=item.title,
                    course_id=course_id,
                )
                chip = status if status == "submitted" else item.kind
            blocks.append(
                assignment_card(
                    ft.Row(
                        [
                            ft.Column(
                                [ft.Text(title, weight=ft.FontWeight.W_600), muted(format_dt(when))],
                                spacing=4,
                                expand=True,
                            ),
                            ft.Column(
                                [
                                    ctrl.countdown_control(when, status=status),
                                    status_chip(chip),
                                ],
                                spacing=4,
                                horizontal_alignment=ft.CrossAxisAlignment.END,
                            ),
                        ]
                    ),
                    course_id=course_id,
                    due_at=when,
                    on_click=lambda e, assignment_id=aid: _open_assignment(ctrl, assignment_id),
                    on_double_tap=lambda e, work=item: ctrl.open_work_in_blackboard(
                        url=getattr(work, "blackboard_url", ""),
                        course_id=course_id,
                        assignment_id=getattr(work, "assignment_id", "") or getattr(work, "id", ""),
                    ),
                )
            )
    else:
        blocks.append(empty_state("No upcoming work for this course."))

    blocks.append(section_title("Grades"))
    if grades:
        for grade in grades:
            blocks.append(
                card(
                    ft.Row(
                        [
                            ft.Text(grade.title, expand=True),
                            ft.Text(grade.score or "—", weight=ft.FontWeight.W_600),
                        ]
                    )
                )
            )
    else:
        blocks.append(empty_state("No grades for this course yet."))

    if notes:
        blocks.append(section_title("Announcements"))
        for note in notes[:5]:
            blocks.append(
                card(
                    ft.Column(
                        [
                            ft.Text(note.title, weight=ft.FontWeight.W_600),
                            muted(note.body or format_dt(note.posted_at, with_time=False)),
                        ],
                        spacing=4,
                    )
                )
            )

    blocks.append(
        ft.OutlinedButton(
            "Open course in Blackboard",
            on_click=lambda e: ctrl.open_blackboard(course.blackboard_url),
        )
    )
    return page_scroll(blocks)


def _open_assignment(ctrl: AppController, assignment_id: str) -> None:
    if ctrl.store.snapshot.assignment_by_id(assignment_id):
        ctrl.go(f"/assignments/{assignment_id}", push=True)
