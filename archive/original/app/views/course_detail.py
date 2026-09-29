from __future__ import annotations

import flet as ft

from blackboard.api import (
    _resolve_assignment_status,
    _trim_number,
    course_result_rows,
    course_score_percent,
    course_score_totals,
    deadline_is_finished,
    grade_note,
    upcoming,
)

from app.controller import AppController
from app.widgets import (
    assignment_card,
    card,
    empty_state,
    format_dt,
    heading,
    list_pager,
    muted,
    page_scroll,
    score_ring,
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
    notes = [n for n in snapshot.announcements if n.course_id == course_id]
    due = [
        deadline
        for deadline in upcoming(snapshot, 21)
        if deadline.course_id == course_id and not deadline_is_finished(snapshot, deadline)
    ]

    totals = course_score_totals(snapshot, course_id)
    percent = course_score_percent(snapshot, course_id)
    fraction = (
        f"{_trim_number(totals[0])} / {_trim_number(totals[1])}"
        if totals
        else "No graded points yet"
    )
    blocks: list[ft.Control] = [
        ft.TextButton("Back", icon=ft.Icons.ARROW_BACK, on_click=lambda e: ctrl.back()),
        ft.Row(
            [
                ft.Column(
                    [
                        heading(course.name),
                        muted(
                            " · ".join(part for part in (course.term, course.instructor) if part)
                            or "Course"
                        ),
                    ],
                    spacing=4,
                    expand=True,
                ),
                ft.Column(
                    [score_ring(percent), muted(fraction, 11)],
                    spacing=4,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        section_title("Upcoming work"),
    ]

    upcoming_items = due or [
        assignment
        for assignment in work
        if _resolve_assignment_status(snapshot, assignment) != "submitted"
    ]
    if upcoming_items:
        upcoming_key = f"course-upcoming:{course_id}"
        upcoming_page, page, page_count, start, total = ctrl.page_window(
            upcoming_key, upcoming_items
        )
        for item in upcoming_page:
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
        pager = list_pager(
            ctrl,
            upcoming_key,
            page=page,
            page_count=page_count,
            start=start,
            total=total,
        )
        if pager is not None:
            blocks.append(pager)
    else:
        blocks.append(empty_state("No upcoming work for this course."))

    blocks.append(section_title("Grades"))
    results = course_result_rows(snapshot, course_id)
    if results:
        grades_key = f"course-grades:{course_id}"
        grade_page, page, page_count, start, total = ctrl.page_window(grades_key, results)
        for title, label, due, aid in grade_page:
            grade = _grade_for_result(snapshot, course_id, title, aid)
            score_bits: list[ft.Control] = [
                ft.Text(label, size=16, weight=ft.FontWeight.W_600),
            ]
            if grade and grade_note(grade):
                score_bits.append(
                    ft.TextButton(
                        "View feedback",
                        icon=ft.Icons.CHAT_BUBBLE_OUTLINE,
                        on_click=lambda e, item=grade: ctrl.show_grade_feedback(item),
                    )
                )
            blocks.append(
                card(
                    ft.Row(
                        [
                            ft.Container(
                                expand=True,
                                ink=bool(aid),
                                on_click=(
                                    lambda e, assignment_id=aid: _open_assignment(ctrl, assignment_id)
                                )
                                if aid
                                else None,
                                content=ft.Column(
                                    [
                                        ft.Text(title, weight=ft.FontWeight.W_600),
                                        muted(format_dt(due, with_time=False) if due else "No due date"),
                                    ],
                                    spacing=2,
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
            )
        pager = list_pager(
            ctrl, grades_key, page=page, page_count=page_count, start=start, total=total
        )
        if pager is not None:
            blocks.append(pager)
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


def _grade_for_result(snapshot, course_id: str, title: str, assignment_id: str):
    for grade in snapshot.grades:
        if grade.course_id != course_id:
            continue
        if assignment_id and assignment_id in {grade.id, grade.assignment_id}:
            return grade
        if grade.title.lower() == title.lower():
            return grade
    return None


def _open_assignment(ctrl: AppController, assignment_id: str) -> None:
    if ctrl.store.snapshot.assignment_by_id(assignment_id):
        ctrl.go(f"/assignments/{assignment_id}", push=True)
