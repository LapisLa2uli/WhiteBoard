from __future__ import annotations

import flet as ft

from blackboard.api import grade_page_groups
from blackboard.models import Grade

from app import theme
from app.controller import AppController
from app.widgets import card, empty_state, error_banner, format_dt, heading, muted, page_scroll


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
        _folder(
            title="Graded",
            subtitle=f"{len(graded)} assignment{'s' if len(graded) != 1 else ''}",
            expanded=ctrl.grades_graded_expanded,
            rows=[_grade_card(ctrl, grade) for grade in graded],
            empty="No graded assignments.",
            on_change=lambda e: ctrl.set_grades_section("graded", _tile_expanded(e)),
        )
    )
    blocks.append(
        _folder(
            title="Submitted, not graded",
            subtitle=f"{len(pending)} assignment{'s' if len(pending) != 1 else ''}",
            expanded=ctrl.grades_pending_expanded,
            rows=[_grade_card(ctrl, grade) for grade in pending],
            empty="No submitted work waiting for a grade.",
            on_change=lambda e: ctrl.set_grades_section("pending", _tile_expanded(e)),
        )
    )
    return page_scroll(blocks)


def _folder(
    *,
    title: str,
    subtitle: str,
    expanded: bool,
    rows: list[ft.Control],
    empty: str,
    on_change,
) -> ft.Control:
    children: list[ft.Control] = rows or [muted(empty)]
    return ft.Container(
        bgcolor=theme.CARD_BG,
        border=ft.Border.all(1, theme.BORDER),
        border_radius=12,
        content=ft.ExpansionTile(
            title=ft.Text(title, weight=ft.FontWeight.W_600, color=theme.TEXT),
            subtitle=ft.Text(subtitle, size=12, color=theme.MUTED),
            leading=ft.Icon(ft.Icons.FOLDER, color=theme.ACCENT),
            expanded=expanded,
            maintain_state=True,
            bgcolor=theme.CARD_BG,
            collapsed_bgcolor=theme.CARD_BG,
            controls_padding=ft.Padding.only(left=12, right=12, bottom=12),
            expanded_alignment=ft.Alignment.TOP_CENTER,
            expanded_cross_axis_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[ft.Column(children, spacing=10, tight=True)],
            on_change=on_change,
        ),
    )


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


def _tile_expanded(event) -> bool:
    data = getattr(event, "data", None)
    if isinstance(data, bool):
        return data
    if isinstance(data, str):
        return data.lower() in {"true", "1", "yes"}
    control = getattr(event, "control", None)
    return bool(getattr(control, "expanded", True))
