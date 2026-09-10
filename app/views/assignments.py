from __future__ import annotations

from datetime import datetime, timezone

import flet as ft

from blackboard.api import assignments_for
from blackboard.models import Assignment

from app import theme
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
    status_chip,
)

FILTERS = ("all", "todo", "submitted", "late")
HIDE_OVERDUE_OPTIONS = (
    ("off", "Show all overdue"),
    ("1w", "Hide if over 1 week late"),
    ("1m", "Hide if over 1 month late"),
)


def build_assignments(ctrl: AppController) -> ft.Control:
    return _build_work_list(
        ctrl,
        title="Assignments",
        subtitle="Unsubmitted work first. Submitted cards are gray and listed underneath. Double-tap a card to open it in Blackboard.",
        show_status_filters=True,
        show_hide_overdue=True,
        forced_status=None,
    )


def build_submitted(ctrl: AppController) -> ft.Control:
    return _build_work_list(
        ctrl,
        title="Submitted",
        subtitle="Work that already has a submission or a grade. Double-tap a card to open it in Blackboard.",
        show_status_filters=False,
        show_hide_overdue=False,
        forced_status="submitted",
    )


def build_ignored(ctrl: AppController) -> ft.Control:
    return _build_work_list(
        ctrl,
        title="Ignored",
        subtitle="Assignments you disregarded. Restore one, or select several and restore them together.",
        show_status_filters=False,
        show_hide_overdue=False,
        forced_status="ignored",
    )


def _build_work_list(
    ctrl: AppController,
    *,
    title: str,
    subtitle: str,
    show_status_filters: bool,
    show_hide_overdue: bool,
    forced_status: str | None,
) -> ft.Control:
    snapshot = ctrl.store.snapshot
    search = ft.TextField(
        hint_text="Search assignments",
        value=ctrl.assignment_query,
        prefix_icon=ft.Icons.SEARCH,
        border_color=theme.BORDER,
        focused_border_color=theme.ACCENT,
        on_change=lambda e: ctrl.set_assignment_query(e.control.value or ""),
    )

    blocks: list[ft.Control] = [
        heading(title),
        muted(subtitle),
        deadline_legend(),
        search,
    ]
    if show_status_filters:
        blocks.append(
            ft.Row(
                [
                    ft.Chip(
                        label=ft.Text(label.title()),
                        selected=ctrl.assignment_filter == label,
                        show_checkmark=False,
                        on_click=lambda e, value=label: _set_filter(ctrl, value),
                    )
                    for label in FILTERS
                ],
                spacing=8,
                wrap=True,
            )
        )
    if show_hide_overdue:
        blocks.append(
            ft.Dropdown(
                label="Overdue work",
                value=ctrl.hide_overdue,
                options=[
                    ft.DropdownOption(key=key, text=label)
                    for key, label in HIDE_OVERDUE_OPTIONS
                ],
                on_select=lambda e: ctrl.set_hide_overdue(e.control.value or "off"),
                width=280,
                border_color=theme.BORDER,
            )
        )
    if snapshot.errors.get("calendar"):
        blocks.append(error_banner("Couldn't load assignments from the calendar. Try Refresh."))

    toolbar = ft.Column(
        assignment_toolbar_controls(ctrl, forced_status=forced_status),
        spacing=8,
    )
    list_column = ft.Column(
        assignment_list_controls(ctrl, forced_status=forced_status),
        spacing=16,
    )
    ctrl.assignment_toolbar_column = toolbar
    ctrl.assignment_list_column = list_column
    ctrl.assignment_list_forced_status = forced_status
    blocks.append(toolbar)
    blocks.append(list_column)
    return page_scroll(blocks)


def visible_assignments(
    ctrl: AppController, *, forced_status: str | None = None
) -> list[Assignment]:
    snapshot = ctrl.store.snapshot
    if forced_status == "ignored":
        items = assignments_for(
            snapshot, "all", query=ctrl.assignment_query, hide_overdue="off"
        )
        return [
            item
            for item in items
            if ctrl.is_ignored_assignment(item)
            and ctrl.assignment_in_active_filter(item.course_id)
        ]
    status = forced_status or ctrl.assignment_filter
    items = assignments_for(
        snapshot,
        status,  # type: ignore[arg-type]
        query=ctrl.assignment_query,
        hide_overdue=ctrl.hide_overdue if forced_status != "submitted" else "off",
    )
    items = [
        item
        for item in items
        if not ctrl.is_ignored_assignment(item)
        and ctrl.assignment_in_active_filter(item.course_id)
    ]
    if (forced_status or ctrl.assignment_filter) == "all":
        items.sort(key=_all_page_sort_key)
    return items


def _all_page_sort_key(assignment: Assignment) -> tuple[bool, datetime]:
    due = assignment.due_at
    if due is None:
        when = datetime.max.replace(tzinfo=timezone.utc)
    elif due.tzinfo is None:
        when = due.replace(tzinfo=timezone.utc)
    else:
        when = due.astimezone(timezone.utc)
    return (assignment.status == "submitted", when)


def assignment_toolbar_controls(
    ctrl: AppController, *, forced_status: str | None = None
) -> list[ft.Control]:
    items = visible_assignments(ctrl, forced_status=forced_status)
    selected_count = sum(1 for item in items if item.id in ctrl.selected_assignment_ids)
    ignored_page = forced_status == "ignored"
    actions = [
        ft.OutlinedButton(
            "Done selecting" if ctrl.assignment_select_mode else "Select",
            icon=ft.Icons.CHECKLIST_OUTLINED,
            on_click=lambda e: ctrl.toggle_assignment_select_mode(),
        )
    ]
    if items:
        actions.append(
            ft.TextButton(
                "Select all",
                on_click=lambda e: ctrl.select_visible_assignments([item.id for item in items]),
            )
        )
    if selected_count:
        if ignored_page:
            actions.append(
                ft.FilledButton(
                    f"Restore selected ({selected_count})",
                    on_click=lambda e: ctrl.restore_selected_assignments(),
                    bgcolor=theme.ACCENT,
                    color="white",
                )
            )
        else:
            actions.append(
                ft.FilledButton(
                    f"Ignore selected ({selected_count})",
                    on_click=lambda e: ctrl.ignore_selected_assignments(),
                    bgcolor=theme.MUTED,
                    color="white",
                )
            )
            markable = sum(
                1
                for item in items
                if item.id in ctrl.selected_assignment_ids and item.status != "submitted"
            )
            if markable:
                actions.append(
                    ft.FilledButton(
                        f"Mark submitted ({markable})",
                        on_click=lambda e: ctrl.mark_selected_assignments_submitted(),
                        bgcolor=theme.OK,
                        color="white",
                    )
                )
    return [
        ft.Row(actions, spacing=8, wrap=True),
        muted("Mark a card submitted, ignore it, or select several to update them together.")
        if not ignored_page
        else muted("Restore a card to put it back on Assignments."),
    ]


def assignment_list_controls(
    ctrl: AppController, *, forced_status: str | None = None
) -> list[ft.Control]:
    snapshot = ctrl.store.snapshot
    items = visible_assignments(ctrl, forced_status=forced_status)
    if not items:
        message = (
            "No matching assignments."
            if ctrl.assignment_query.strip()
            else "No ignored assignments."
            if forced_status == "ignored"
            else "No assignments in this filter."
        )
        return [empty_state(message, ctrl.refresh)]

    ignored_page = forced_status == "ignored"
    rows: list[ft.Control] = []
    for assignment in items:
        course = snapshot.course_name(assignment.course_id)
        selected = assignment.id in ctrl.selected_assignment_ids
        submitted = assignment.status == "submitted"
        title_color = theme.MUTED if submitted else theme.TEXT
        card = assignment_card(
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                assignment.title,
                                weight=ft.FontWeight.W_600,
                                color=title_color,
                            ),
                            muted(f"{course or 'Course'}  ·  {format_dt(assignment.due_at)}"),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    ft.Column(
                        [
                            ctrl.countdown_control(
                                assignment.due_at, status=assignment.status
                            ),
                            status_chip(assignment.status),
                        ],
                        spacing=4,
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                    ),
                ]
            ),
            course_id=assignment.course_id,
            due_at=assignment.due_at,
            dimmed=submitted,
            on_click=lambda e, aid=assignment.id: _on_card_click(ctrl, aid),
            on_double_tap=lambda e, item=assignment: ctrl.open_work_in_blackboard(
                url=item.blackboard_url,
                course_id=item.course_id,
                assignment_id=item.id,
            ),
        )
        leading: list[ft.Control] = []
        if ctrl.assignment_select_mode:
            leading.append(
                ft.Checkbox(
                    value=selected,
                    on_change=lambda e, aid=assignment.id: ctrl.toggle_assignment_selected(aid),
                )
            )
        action = (
            ft.IconButton(
                icon=ft.Icons.VISIBILITY_OUTLINED,
                tooltip="Restore",
                icon_color=theme.ACCENT,
                on_click=lambda e, item=assignment: ctrl.restore_assignments([item]),
            )
            if ignored_page
            else ft.IconButton(
                icon=ft.Icons.VISIBILITY_OFF_OUTLINED,
                tooltip="Ignore",
                icon_color=theme.MUTED,
                on_click=lambda e, item=assignment: ctrl.ignore_assignments([item]),
            )
        )
        status_action: ft.Control = ft.Container(width=0, height=0)
        if not ignored_page:
            if ctrl.is_marked_submitted(assignment):
                status_action = ft.IconButton(
                    icon=ft.Icons.UNDO,
                    tooltip="Undo submitted mark",
                    icon_color=theme.MUTED,
                    on_click=lambda e, item=assignment: ctrl.unmark_assignments_submitted([item]),
                )
            elif assignment.status != "submitted":
                status_action = ft.IconButton(
                    icon=ft.Icons.TASK_ALT,
                    tooltip="Mark as submitted",
                    icon_color=theme.OK,
                    on_click=lambda e, item=assignment: ctrl.mark_assignments_submitted([item]),
                )
        rows.append(
            ft.Row(
                [*leading, ft.Container(content=card, expand=True), status_action, action],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
    return rows


def _on_card_click(ctrl: AppController, assignment_id: str) -> None:
    if ctrl.assignment_select_mode:
        ctrl.toggle_assignment_selected(assignment_id)
        return
    ctrl.go(f"/assignments/{assignment_id}", push=True)


def _set_filter(ctrl: AppController, value: str) -> None:
    ctrl.assignment_filter = value
    ctrl.selected_assignment_ids.clear()
    ctrl.rebuild()
