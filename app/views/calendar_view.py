from __future__ import annotations

from itertools import groupby

import flet as ft

from blackboard.api import upcoming

from app.controller import AppController
from app.widgets import (
    assignment_card,
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


def build_calendar(ctrl: AppController) -> ft.Control:
    snapshot = ctrl.store.snapshot
    items = [
        item
        for item in upcoming(snapshot, ctrl.calendar_days)
        if ctrl.assignment_in_active_filter(item.course_id)
    ]

    toggles = ft.Row(
        [
            ft.Chip(
                label=ft.Text(f"{days} days"),
                selected=ctrl.calendar_days == days,
                show_checkmark=False,
                on_click=lambda e, value=days: _set_days(ctrl, value),
            )
            for days in (7, 14, 30)
        ],
        spacing=8,
    )

    blocks: list[ft.Control] = [
        heading("Calendar"),
        muted("Upcoming deadlines grouped by day."),
        deadline_legend(),
        toggles,
    ]
    if snapshot.errors.get("calendar"):
        blocks.append(error_banner("Couldn't load the calendar. Try Refresh."))

    if not items:
        blocks.append(empty_state("No upcoming deadlines in this range.", ctrl.refresh))
        return page_scroll(blocks)

    def day_key(item):
        when = item.when
        return when.date() if when else None

    for day, group in groupby(items, key=day_key):
        label = day.strftime("%A, %B %d") if day else "No date"
        blocks.append(section_title(label))
        for item in group:
            course = snapshot.course_name(item.course_id)

            def open_item(e, deadline=item):
                aid = deadline.assignment_id or deadline.id
                if deadline.kind == "assignment" and snapshot.assignment_by_id(aid):
                    ctrl.go(f"/assignments/{aid}", push=True)
                else:
                    ctrl.go(f"/assignments/{deadline.id}", push=True)

            blocks.append(
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
                                            assignment_id=item.assignment_id or item.id,
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
                        ]
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
    return page_scroll(blocks)


def _set_days(ctrl: AppController, days: int) -> None:
    ctrl.calendar_days = days
    ctrl.rebuild()
