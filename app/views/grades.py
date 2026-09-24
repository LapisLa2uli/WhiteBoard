from __future__ import annotations

import flet as ft

from blackboard.api import (
    _trim_number,
    course_score_percent,
    course_score_totals,
    format_grade_label,
    grade_due_at,
    grade_page_groups,
)
from blackboard.models import Grade

from app import theme
from app.controller import AppController
from app.widgets import (
    collapsible_folder,
    empty_state,
    error_banner,
    format_dt,
    heading,
    muted,
    page_scroll,
    subject_fill,
    subject_ink,
    tile_expanded,
)


def build_grades(ctrl: AppController) -> ft.Control:
    snapshot = ctrl.store.snapshot
    graded, pending = grade_page_groups(snapshot)
    graded = [row for row in graded if ctrl.assignment_in_active_filter(row.course_id)]
    pending = [row for row in pending if ctrl.assignment_in_active_filter(row.course_id)]

    blocks: list[ft.Control] = [
        heading("Grades"),
        muted("Posted scores and submitted work waiting for a grade. Unsubmitted work is hidden."),
    ]
    if snapshot.errors.get("grades"):
        blocks.append(error_banner("Couldn't load grades. Try Refresh."))

    score_lines = _course_score_lines(ctrl)
    if score_lines:
        blocks.append(ft.Column(score_lines, spacing=14))

    graded.sort(key=lambda grade: _due_stamp(snapshot, grade), reverse=True)

    if not graded and not pending:
        blocks.append(empty_state("No graded or submitted assignments.", ctrl.refresh))
        return page_scroll(blocks)

    blocks.append(
        collapsible_folder(
            title="Graded",
            subtitle=f"{len(graded)} assignment{'s' if len(graded) != 1 else ''}",
            expanded=ctrl.grades_graded_expanded,
            rows=[_grade_card(ctrl, grade) for grade in graded],
            empty="No graded assignments.",
            on_change=lambda e: ctrl.set_grades_section("graded", tile_expanded(e)),
        )
    )
    blocks.append(
        collapsible_folder(
            title="Submitted, not graded",
            subtitle=f"{len(pending)} assignment{'s' if len(pending) != 1 else ''}",
            expanded=ctrl.grades_pending_expanded,
            rows=[_grade_card(ctrl, grade) for grade in pending],
            empty="No submitted work waiting for a grade.",
            on_change=lambda e: ctrl.set_grades_section("pending", tile_expanded(e)),
        )
    )
    return page_scroll(blocks)


def _course_score_lines(ctrl: AppController) -> list[ft.Control]:
    snapshot = ctrl.store.snapshot
    lines: list[ft.Control] = []
    for course, hidden in ctrl.listed_courses():
        if hidden and ctrl.hide_filtered_assignments:
            continue
        percent = course_score_percent(snapshot, course.id)
        totals = course_score_totals(snapshot, course.id)
        if percent is None or totals is None:
            continue
        ink = subject_ink(course.id)
        lines.append(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(width=10, height=10, border_radius=5, bgcolor=ink),
                            ft.Text(
                                course.name,
                                expand=True,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(f"{round(percent)}%", weight=ft.FontWeight.W_700, color=ink),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.ProgressBar(
                        value=max(0.0, min(1.0, percent / 100)),
                        color=ink,
                        bgcolor=theme.BORDER,
                        bar_height=8,
                    ),
                    muted(
                        f"{_trim_number(totals[0])} / {_trim_number(totals[1])} points"
                    ),
                ],
                spacing=4,
            )
        )
    return lines


def _due_stamp(snapshot, grade: Grade) -> float:
    due = grade_due_at(snapshot, grade)
    if due is None:
        return float("-inf")
    stamp = due.timestamp()
    return stamp


def _grade_card(ctrl: AppController, grade: Grade) -> ft.Control:
    snapshot = ctrl.store.snapshot
    course = snapshot.course_name(grade.course_id) or "Course"
    due = grade_due_at(snapshot, grade)
    due_label = format_dt(due, with_time=False) if due else "No due date"
    ink = subject_ink(grade.course_id)

    def open_row(e, aid=grade.assignment_id, cid=grade.course_id):
        if aid and snapshot.assignment_by_id(aid):
            ctrl.go(f"/assignments/{aid}", push=True)
        elif cid:
            ctrl.go(f"/courses/{cid}", push=True)

    return ft.Container(
        bgcolor=subject_fill(grade.course_id),
        border=ft.Border.all(1, ink),
        border_radius=12,
        padding=16,
        ink=True,
        on_click=open_row,
        content=ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(grade.title, weight=ft.FontWeight.W_600, color=theme.TEXT),
                        muted(f"{course}  ·  {due_label}"),
                    ],
                    spacing=4,
                    expand=True,
                ),
                ft.Text(format_grade_label(grade), size=16, weight=ft.FontWeight.W_700, color=ink),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )
