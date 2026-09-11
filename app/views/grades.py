from __future__ import annotations

import flet as ft

from blackboard.api import grade_page_groups
from blackboard.models import Grade

from app.controller import AppController
from app.widgets import (
    card,
    collapsible_folder,
    empty_state,
    error_banner,
    format_dt,
    heading,
    muted,
    page_scroll,
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


def _grade_card(ctrl: AppController, grade: Grade) -> ft.Control:
    snapshot = ctrl.store.snapshot
    course = snapshot.course_name(grade.course_id)
    posted = format_dt(grade.posted_at, with_time=False)
    detail = course or "Course"
    if grade.posted_at:
        detail = f"{detail}  ·  {posted}"

    def open_row(e, aid=grade.assignment_id, cid=grade.course_id):
        if aid and snapshot.assignment_by_id(aid):
            ctrl.go(f"/assignments/{aid}", push=True)
        elif cid:
            ctrl.go(f"/courses/{cid}", push=True)

    return card(
        ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(grade.title, weight=ft.FontWeight.W_600),
                        muted(detail),
                    ],
                    spacing=4,
                    expand=True,
                ),
                ft.Text(grade.score or "—", size=16, weight=ft.FontWeight.W_600),
            ]
        ),
        on_click=open_row,
    )
