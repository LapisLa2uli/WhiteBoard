from __future__ import annotations

import flet as ft

from app.controller import AppController
from app.widgets import assignment_card, card, format_dt, heading, muted, page_scroll, status_chip


def build_assignment_detail(ctrl: AppController, assignment_id: str) -> ft.Control:
    snapshot = ctrl.store.snapshot
    assignment = snapshot.assignment_by_id(assignment_id)
    if not assignment:
        deadline = next((d for d in snapshot.deadlines if d.id == assignment_id), None)
        if deadline:
            return _deadline_panel(ctrl, deadline)
        return page_scroll(
            [
                ft.TextButton("Back", icon=ft.Icons.ARROW_BACK, on_click=lambda e: ctrl.back()),
                heading("Item not found"),
                muted("This assignment is not in the current snapshot."),
            ]
        )

    course = snapshot.course_by_id(assignment.course_id)
    grade = next(
        (
            g
            for g in snapshot.grades
            if g.assignment_id == assignment.id
            or (g.course_id == assignment.course_id and g.title.lower() == assignment.title.lower())
        ),
        None,
    )

    details = [
        ft.Row(
            [
                muted("Course"),
                ft.TextButton(
                    course.name if course else assignment.course_id or "Unknown course",
                    on_click=lambda e: _open_course(ctrl, assignment.course_id),
                ),
            ]
        ),
        ft.Row([muted("Due"), ft.Text(format_dt(assignment.due_at))]),
        ft.Row([muted("Status"), status_chip(assignment.status)]),
    ]
    if assignment.status in {"todo", "late"}:
        details.insert(
            2,
            ft.Row(
                [
                    muted("Time left"),
                    ctrl.countdown_control(assignment.due_at, status=assignment.status),
                ]
            ),
        )
    if grade:
        details.append(ft.Row([muted("Grade"), ft.Text(grade.score or "—", weight=ft.FontWeight.W_600)]))

    blocks: list[ft.Control] = [
        ft.TextButton("Back", icon=ft.Icons.ARROW_BACK, on_click=lambda e: ctrl.back()),
        heading(assignment.title),
        assignment_card(
            ft.Column(details, spacing=10),
            course_id=assignment.course_id,
            due_at=assignment.due_at,
            on_double_tap=lambda e: ctrl.open_work_in_blackboard(
                url=assignment.blackboard_url,
                course_id=assignment.course_id,
                assignment_id=assignment.id,
            ),
        ),
    ]
    if assignment.description:
        blocks.append(card(ft.Column([muted("Description"), ft.Text(assignment.description)], spacing=6)))
    blocks.append(
        ft.OutlinedButton(
            "Open in Blackboard",
            on_click=lambda e: ctrl.open_work_in_blackboard(
                url=assignment.blackboard_url,
                course_id=assignment.course_id,
                assignment_id=assignment.id,
            ),
        )
    )
    return page_scroll(blocks)


def _deadline_panel(ctrl: AppController, deadline) -> ft.Control:
    course = ctrl.store.snapshot.course_name(deadline.course_id)
    status = ctrl.countdown_status(
        assignment_id=deadline.assignment_id or deadline.id,
        kind=deadline.kind,
    )
    rows = [
        ft.Row([muted("When"), ft.Text(format_dt(deadline.when))]),
    ]
    if status in {"todo", "late"}:
        rows.append(
            ft.Row(
                [
                    muted("Time left"),
                    ctrl.countdown_control(deadline.when, status=status),
                ]
            )
        )
    rows.extend(
        [
            ft.Row([muted("Course"), ft.Text(course or "—")]),
            ft.Row([muted("Type"), status_chip(deadline.kind)]),
        ]
    )
    return page_scroll(
        [
            ft.TextButton("Back", icon=ft.Icons.ARROW_BACK, on_click=lambda e: ctrl.back()),
            heading(deadline.title),
            assignment_card(
                ft.Column(
                    rows,
                    spacing=10,
                ),
                course_id=deadline.course_id,
                due_at=deadline.when,
                on_double_tap=lambda e: ctrl.open_work_in_blackboard(
                    url=deadline.blackboard_url,
                    course_id=deadline.course_id,
                    assignment_id=deadline.id,
                ),
            ),
            ft.OutlinedButton(
                "Open in Blackboard",
                on_click=lambda e: ctrl.open_work_in_blackboard(
                    url=deadline.blackboard_url,
                    course_id=deadline.course_id,
                    assignment_id=deadline.id,
                ),
            ),
        ]
    )


def _open_course(ctrl: AppController, course_id: str) -> None:
    if course_id and ctrl.store.snapshot.course_by_id(course_id):
        ctrl.go(f"/courses/{course_id}", push=True)
