from __future__ import annotations

import flet as ft

from blackboard.api import (
    _trim_number,
    course_score_percent,
    course_score_totals,
    format_grade_label,
    grade_due_at,
    grade_note,
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
    list_pager,
    muted,
    page_scroll,
    subject_fill,
    subject_ink,
    tile_expanded,
)


def build_grades(ctrl: AppController) -> ft.Control:
    snapshot = ctrl.store.snapshot
    search = ft.TextField(
        hint_text="Search grades",
        value=ctrl.grade_query,
        prefix_icon=ft.Icons.SEARCH,
        border_color=theme.BORDER,
        focused_border_color=theme.ACCENT,
        on_change=lambda e: ctrl.set_grade_query(e.control.value or ""),
    )
    blocks: list[ft.Control] = [
        heading("Grades"),
        muted("Posted scores and submitted work waiting for a grade. Unsubmitted work is hidden."),
        search,
    ]
    if snapshot.errors.get("grades"):
        blocks.append(error_banner("Couldn't load grades. Try Refresh."))

    score_lines = _course_score_lines(ctrl)
    if score_lines:
        blocks.append(ft.Column(score_lines, spacing=14))

    grade_list = ft.Column(grade_list_controls(ctrl), spacing=16)
    ctrl.grades_list_column = grade_list
    blocks.append(grade_list)
    return page_scroll(blocks)


def grade_list_controls(ctrl: AppController) -> list[ft.Control]:
    snapshot = ctrl.store.snapshot
    graded, pending = grade_page_groups(snapshot)
    graded = [row for row in graded if ctrl.assignment_in_active_filter(row.course_id)]
    pending = [row for row in pending if ctrl.assignment_in_active_filter(row.course_id)]
    query = ctrl.grade_query.strip().lower()

    def matches(grade: Grade) -> bool:
        if not query:
            return True
        course = (snapshot.course_name(grade.course_id) or "").lower()
        haystack = " ".join(
            (grade.title, course, format_grade_label(grade), grade_note(grade))
        ).lower()
        return query in haystack

    graded = [row for row in graded if matches(row)]
    pending = [row for row in pending if matches(row)]
    graded.sort(key=lambda grade: _due_stamp(snapshot, grade), reverse=True)

    if not graded and not pending:
        message = "No grades match your search." if query else "No graded or submitted assignments."
        return [empty_state(message, ctrl.refresh)]

    return [
        collapsible_folder(
            title="Graded",
            subtitle=f"{len(graded)} assignment{'s' if len(graded) != 1 else ''}",
            expanded=ctrl.grades_graded_expanded,
            rows=_paged_grade_rows(ctrl, "grades-graded", graded),
            empty="No graded assignments.",
            on_change=lambda e: ctrl.set_grades_section("graded", tile_expanded(e)),
        ),
        collapsible_folder(
            title="Submitted, not graded",
            subtitle=f"{len(pending)} assignment{'s' if len(pending) != 1 else ''}",
            expanded=ctrl.grades_pending_expanded,
            rows=_paged_grade_rows(ctrl, "grades-pending", pending),
            empty="No submitted work waiting for a grade.",
            on_change=lambda e: ctrl.set_grades_section("pending", tile_expanded(e)),
        ),
    ]


def _paged_grade_rows(ctrl: AppController, key: str, grades: list[Grade]) -> list[ft.Control]:
    if not grades:
        return []
    window, page, page_count, start, total = ctrl.page_window(key, grades)
    rows: list[ft.Control] = [_grade_card(ctrl, grade) for grade in window]
    pager = list_pager(ctrl, key, page=page, page_count=page_count, start=start, total=total)
    if pager is not None:
        rows.append(pager)
    return rows


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

    score_bits: list[ft.Control] = [
        ft.Text(format_grade_label(grade), size=16, weight=ft.FontWeight.W_700, color=ink),
    ]
    if grade_note(grade):
        score_bits.append(
            ft.TextButton(
                "View feedback",
                icon=ft.Icons.CHAT_BUBBLE_OUTLINE,
                on_click=lambda e, item=grade: ctrl.show_grade_feedback(item),
            )
        )

    return ft.Container(
        bgcolor=subject_fill(grade.course_id),
        border=ft.Border.all(1, ink),
        border_radius=12,
        padding=16,
        content=ft.Row(
            [
                ft.Container(
                    expand=True,
                    ink=True,
                    on_click=open_row,
                    content=ft.Column(
                        [
                            ft.Text(grade.title, weight=ft.FontWeight.W_600, color=theme.TEXT),
                            muted(f"{course}  ·  {due_label}"),
                        ],
                        spacing=4,
                    ),
                ),
                ft.Column(
                    score_bits,
                    spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )
