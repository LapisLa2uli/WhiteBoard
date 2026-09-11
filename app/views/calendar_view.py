from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from itertools import groupby

import flet as ft

from blackboard.api import (
    add_months,
    calendar_items_in_range,
    calendar_week_start,
    deadline_is_finished,
    event_is_all_day,
    local_event_date,
    upcoming,
)

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
    subject_fill,
    subject_ink,
)

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTH_CHIP_LIMIT = 3


def build_calendar(ctrl: AppController) -> ft.Control:
    snapshot = ctrl.store.snapshot
    mode = ctrl.calendar_mode if ctrl.calendar_mode in {"list", "week", "month"} else "list"

    blocks: list[ft.Control] = [
        heading("Calendar"),
        muted("Assignments, tests, and other Blackboard calendar events."),
        deadline_legend(),
        _toolbar(ctrl, mode),
    ]
    if snapshot.errors.get("calendar"):
        blocks.append(error_banner("Couldn't load the calendar. Try Refresh."))

    if mode == "month":
        blocks.append(_month_grid(ctrl))
    elif mode == "week":
        blocks.append(_week_grid(ctrl))
    else:
        blocks.extend(_list_blocks(ctrl))
    return page_scroll(blocks)


def _toolbar(ctrl: AppController, mode: str) -> ft.Control:
    chips = [
        ft.Chip(
            label=ft.Text(label),
            selected=mode == key,
            show_checkmark=False,
            on_click=lambda e, value=key: ctrl.set_calendar_mode(value),
        )
        for key, label in (("list", "List"), ("week", "Week"), ("month", "Month"))
    ]
    nav = ft.Row(
        [
            ft.OutlinedButton("Today", on_click=lambda e: ctrl.calendar_go_today()),
            ft.IconButton(
                icon=ft.Icons.CHEVRON_LEFT,
                tooltip="Previous",
                on_click=lambda e: ctrl.shift_calendar(-1),
            ),
            ft.IconButton(
                icon=ft.Icons.CHEVRON_RIGHT,
                tooltip="Next",
                on_click=lambda e: ctrl.shift_calendar(1),
            ),
            ft.Text(_period_title(ctrl, mode), size=20, weight=ft.FontWeight.W_600),
        ],
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        wrap=True,
    )
    controls: list[ft.Control] = [
        nav,
        ft.Row(chips, spacing=8),
    ]
    if mode == "list":
        controls.append(
            ft.Row(
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
        )
    return ft.Column(controls, spacing=10)


def _period_title(ctrl: AppController, mode: str) -> str:
    anchor = ctrl.calendar_anchor
    if mode == "month":
        return anchor.strftime("%B %Y")
    if mode == "week":
        start = calendar_week_start(anchor)
        end = start + timedelta(days=6)
        if start.month == end.month:
            return f"{start.strftime('%b')} {start.day} – {end.day}, {end.year}"
        return f"{start.strftime('%b')} {start.day} – {end.strftime('%b')} {end.day}, {end.year}"
    if ctrl.calendar_anchor == date.today():
        return f"Next {ctrl.calendar_days} days"
    return f"From {anchor.strftime('%b')} {anchor.day}"


def _list_blocks(ctrl: AppController) -> list[ft.Control]:
    snapshot = ctrl.store.snapshot
    origin = (
        datetime.now(timezone.utc)
        if ctrl.calendar_anchor == date.today()
        else _day_start(ctrl.calendar_anchor)
    )
    items = [
        item
        for item in upcoming(snapshot, ctrl.calendar_days, now=origin)
        if ctrl.assignment_in_active_filter(item.course_id) or not item.course_id
    ]
    if not items:
        return [empty_state("No upcoming events in this range.", ctrl.refresh)]

    blocks: list[ft.Control] = []

    def day_key(item):
        return local_event_date(item.when)

    for day, group in groupby(items, key=day_key):
        label = day.strftime("%A, %B %d") if day else "No date"
        blocks.append(ft.Text(label, size=16, weight=ft.FontWeight.W_600, color=theme.TEXT))
        for item in group:
            blocks.append(_list_card(ctrl, item))
    return blocks


def _list_card(ctrl: AppController, item) -> ft.Control:
    snapshot = ctrl.store.snapshot
    course = snapshot.course_name(item.course_id)
    finished = item.kind != "other" and deadline_is_finished(snapshot, item)

    def open_item(e, deadline=item):
        _open_calendar_item(ctrl, deadline)

    return assignment_card(
        ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(
                            item.title,
                            weight=ft.FontWeight.W_600,
                            color=theme.MUTED if finished else theme.TEXT,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        muted(
                            f"{format_dt(item.when)}  ·  {course or _kind_label(item.kind)}",
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
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
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        course_id=item.course_id,
        due_at=item.when,
        dimmed=finished,
        on_click=open_item,
        on_double_tap=lambda e, deadline=item: ctrl.open_work_in_blackboard(
            url=deadline.blackboard_url,
            course_id=deadline.course_id,
            assignment_id=deadline.assignment_id or deadline.id,
        ),
    )


def _month_grid(ctrl: AppController) -> ft.Control:
    snapshot = ctrl.store.snapshot
    today = date.today()
    month_start = ctrl.calendar_anchor.replace(day=1)
    grid_start = calendar_week_start(month_start)
    month_end = add_months(month_start, 1)
    range_start = _day_start(grid_start)
    range_end = _day_start(grid_start + timedelta(days=42))
    events = [
        item
        for item in calendar_items_in_range(snapshot, range_start, range_end)
        if ctrl.assignment_in_active_filter(item.course_id) or not item.course_id
    ]
    by_day: dict[date, list] = {}
    for item in events:
        day = local_event_date(item.when)
        if day is None:
            continue
        by_day.setdefault(day, []).append(item)

    header = ft.Row(
        [
            ft.Container(
                expand=True,
                content=ft.Text(
                    name,
                    size=12,
                    weight=ft.FontWeight.W_600,
                    color=theme.MUTED,
                    text_align=ft.TextAlign.CENTER,
                ),
                padding=ft.Padding.only(bottom=6),
            )
            for name in WEEKDAYS
        ],
        spacing=0,
    )
    rows: list[ft.Control] = [header]
    for week in range(6):
        cells = []
        for offset in range(7):
            day = grid_start + timedelta(days=week * 7 + offset)
            cells.append(
                _month_cell(
                    ctrl,
                    day,
                    in_month=month_start <= day < month_end,
                    events=by_day.get(day, []),
                    today=today,
                )
            )
        rows.append(ft.Row(cells, spacing=0, expand=True))
    return ft.Container(
        bgcolor=theme.CARD_BG,
        border=ft.Border.all(1, theme.BORDER),
        border_radius=12,
        padding=8,
        content=ft.Column(rows, spacing=0),
    )


def _month_cell(ctrl, day: date, *, in_month: bool, events: list, today: date) -> ft.Control:
    is_today = day == today
    number_color = "white" if is_today else (theme.TEXT if in_month else theme.MUTED)
    number = ft.Container(
        width=26,
        height=26,
        border_radius=13,
        bgcolor=theme.ACCENT if is_today else None,
        alignment=ft.Alignment.CENTER,
        content=ft.Text(str(day.day), size=12, weight=ft.FontWeight.W_600, color=number_color),
    )
    visible = events[:MONTH_CHIP_LIMIT]
    extra = len(events) - MONTH_CHIP_LIMIT
    chips: list[ft.Control] = [_event_chip(ctrl, item) for item in visible]
    if extra > 0:
        chips.append(muted(f"+{extra} more", 11))
    return ft.Container(
        expand=True,
        height=118,
        padding=6,
        bgcolor="#dbeafe" if is_today else (theme.CARD_BG if in_month else "#f8fafc"),
        border=ft.Border.all(1, theme.BORDER),
        content=ft.Column([number, *chips], spacing=3, expand=True, scroll=ft.ScrollMode.AUTO),
    )


def _week_grid(ctrl: AppController) -> ft.Control:
    snapshot = ctrl.store.snapshot
    today = date.today()
    start = calendar_week_start(ctrl.calendar_anchor)
    range_start = _day_start(start)
    range_end = _day_start(start + timedelta(days=7))
    events = [
        item
        for item in calendar_items_in_range(snapshot, range_start, range_end)
        if ctrl.assignment_in_active_filter(item.course_id) or not item.course_id
    ]
    by_day: dict[date, list] = {start + timedelta(days=i): [] for i in range(7)}
    for item in events:
        day = local_event_date(item.when)
        if day in by_day:
            by_day[day].append(item)

    header = ft.Row(
        [
            _week_header_cell(start + timedelta(days=i), today)
            for i in range(7)
        ],
        spacing=0,
    )
    all_day_row = ft.Row(
        [
            _week_stack(
                ctrl,
                [
                    item
                    for item in by_day[start + timedelta(days=i)]
                    if event_is_all_day(item.when)
                ],
                empty="All day",
            )
            for i in range(7)
        ],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
    timed_row = ft.Row(
        [
            _week_stack(
                ctrl,
                [
                    item
                    for item in by_day[start + timedelta(days=i)]
                    if not event_is_all_day(item.when)
                ],
                empty="",
                min_height=280,
            )
            for i in range(7)
        ],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
    return ft.Container(
        bgcolor=theme.CARD_BG,
        border=ft.Border.all(1, theme.BORDER),
        border_radius=12,
        padding=8,
        content=ft.Column(
            [
                header,
                muted("All-day", 11),
                all_day_row,
                ft.Divider(color=theme.BORDER),
                timed_row,
            ],
            spacing=8,
        ),
    )


def _week_header_cell(day: date, today: date) -> ft.Control:
    is_today = day == today
    return ft.Container(
        expand=True,
        padding=8,
        content=ft.Column(
            [
                ft.Text(WEEKDAYS[day.weekday()], size=11, color=theme.MUTED),
                ft.Container(
                    width=28,
                    height=28,
                    border_radius=14,
                    bgcolor=theme.ACCENT if is_today else None,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text(
                        str(day.day),
                        size=16,
                        weight=ft.FontWeight.W_600,
                        color="white" if is_today else theme.TEXT,
                    ),
                ),
            ],
            spacing=2,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def _week_stack(ctrl, items: list, *, empty: str, min_height: int = 72) -> ft.Control:
    chips = [_event_chip(ctrl, item, show_time=not event_is_all_day(item.when)) for item in items]
    if not chips and empty:
        chips = [muted(empty, 11)]
    return ft.Container(
        expand=True,
        padding=4,
        border=ft.Border.all(1, theme.BORDER),
        bgcolor=theme.PAGE_BG,
        content=ft.Column(chips, spacing=4, scroll=ft.ScrollMode.AUTO),
        height=min_height,
    )


def _event_chip(ctrl: AppController, item, *, show_time: bool = False) -> ft.Control:
    snapshot = ctrl.store.snapshot
    finished = item.kind != "other" and deadline_is_finished(snapshot, item)
    label = item.title
    if show_time and item.when:
        local = item.when.astimezone() if item.when.tzinfo else item.when.replace(tzinfo=timezone.utc).astimezone()
        label = f"{local.strftime('%H:%M')} {item.title}"
    fill = "#e2e8f0" if finished else subject_fill(item.course_id)
    ink = theme.MUTED if finished else subject_ink(item.course_id)
    return ft.Container(
        content=ft.Text(
            label,
            size=11,
            color=ink,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            weight=ft.FontWeight.W_500,
        ),
        bgcolor=fill,
        padding=ft.Padding.symmetric(horizontal=6, vertical=3),
        border_radius=6,
        on_click=lambda e, deadline=item: _open_calendar_item(ctrl, deadline),
        ink=True,
    )


def _open_calendar_item(ctrl: AppController, deadline) -> None:
    snapshot = ctrl.store.snapshot
    aid = deadline.assignment_id or deadline.id
    if deadline.kind == "assignment" and snapshot.assignment_by_id(aid):
        ctrl.go(f"/assignments/{aid}", push=True)
        return
    if aid and snapshot.assignment_by_id(aid):
        ctrl.go(f"/assignments/{aid}", push=True)
        return
    if deadline.course_id:
        ctrl.go(f"/courses/{deadline.course_id}", push=True)
        return
    ctrl.open_work_in_blackboard(
        url=deadline.blackboard_url,
        course_id=deadline.course_id,
        assignment_id=aid,
    )


def _kind_label(kind: str) -> str:
    return {"assignment": "Assignment", "test": "Test", "other": "Event"}.get(kind, "Event")


def _day_start(day: date) -> datetime:
    tzinfo = datetime.now().astimezone().tzinfo
    return datetime(day.year, day.month, day.day, tzinfo=tzinfo)


def _set_days(ctrl: AppController, days: int) -> None:
    ctrl.calendar_days = days
    ctrl.rebuild()
