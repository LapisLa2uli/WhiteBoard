"""Turn a saved Blackboard snapshot into the data the slim UI renders."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blackboard.api import (
    course_result_rows,
    course_score_percent,
    course_score_totals,
    deadline_is_finished,
    format_grade_label,
    grade_note,
    grade_page_groups,
    local_event_date,
    recent_grades,
    upcoming,
)
from blackboard.models import Snapshot
from blackboard.store import SNAPSHOT_PATH, load_settings

from app.palette import deadline_color, subject_fill, subject_ink, apply_palette


def load_snapshot() -> Snapshot:
    if not SNAPSHOT_PATH.exists():
        return Snapshot()
    import json

    data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return Snapshot.from_dict(data)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def format_dt(value: datetime | None, *, with_time: bool = True) -> str:
    if value is None:
        return "No date"
    local = _as_utc(value).astimezone()
    if with_time:
        return local.strftime("%a %b %d, %H:%M")
    return local.strftime("%a %b %d")


def format_countdown(due_at: datetime | None, *, now: datetime | None = None) -> str:
    if due_at is None:
        return ""
    moment = now or datetime.now(timezone.utc)
    seconds = int((_as_utc(due_at) - _as_utc(moment)).total_seconds())
    overdue = seconds < 0
    seconds = abs(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    clock = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    body = f"{days}d {clock}" if days else clock
    return f"Overdue {body}" if overdue else f"Due in {body}"


def deadline_border(due_at: datetime | None) -> str:
    if due_at is None:
        return "#94a3b8"
    hours = (_as_utc(due_at) - datetime.now(timezone.utc)).total_seconds() / 3600
    if hours < 0:
        return deadline_color("overdue")
    if hours <= 24:
        return deadline_color("today")
    if hours <= 72:
        return deadline_color("soon")
    if hours <= 168:
        return deadline_color("week")
    return deadline_color("later")


def build_state(snapshot: Snapshot | None = None) -> dict:
    settings = load_settings()
    apply_palette(settings)
    snapshot = snapshot or load_snapshot()
    courses = [
        {
            "id": course.id,
            "name": course.name,
            "fill": subject_fill(course.id),
            "ink": subject_ink(course.id),
        }
        for course in snapshot.courses
    ]
    course_name = {course.id: course.name for course in snapshot.courses}

    def pack_deadline(item) -> dict:
        aid = item.assignment_id or (item.id if item.kind == "assignment" else "")
        return {
            "id": item.id,
            "title": item.title,
            "course_id": item.course_id,
            "course": course_name.get(item.course_id, ""),
            "when": format_dt(item.when),
            "when_date": format_dt(item.when, with_time=False),
            "day": (local_event_date(item.when).isoformat() if item.when else ""),
            "day_label": (
                local_event_date(item.when).strftime("%A, %B %d") if item.when else "No date"
            ),
            "kind": item.kind,
            "countdown": format_countdown(item.when),
            "border": deadline_border(item.when),
            "fill": subject_fill(item.course_id),
            "url": item.blackboard_url,
            "assignment_id": aid,
            "finished": deadline_is_finished(snapshot, item),
        }

    assignments = []
    for item in snapshot.assignments:
        assignments.append(
            {
                "id": item.id,
                "title": item.title,
                "course_id": item.course_id,
                "course": course_name.get(item.course_id, ""),
                "when": format_dt(item.due_at),
                "status": item.status,
                "description": item.description,
                "countdown": format_countdown(item.due_at),
                "border": deadline_border(item.due_at),
                "fill": subject_fill(item.course_id),
                "url": item.blackboard_url,
                "handler": item.content_handler,
            }
        )

    graded, pending = grade_page_groups(snapshot)
    def pack_grade(grade) -> dict:
        return {
            "id": grade.id,
            "title": grade.title,
            "course_id": grade.course_id,
            "course": course_name.get(grade.course_id, ""),
            "label": format_grade_label(grade),
            "note": grade_note(grade),
            "fill": subject_fill(grade.course_id),
            "ink": subject_ink(grade.course_id),
            "assignment_id": grade.assignment_id,
            "due": format_dt(grade.posted_at, with_time=False),
        }

    score_lines = []
    for course in snapshot.courses:
        percent = course_score_percent(snapshot, course.id)
        totals = course_score_totals(snapshot, course.id)
        if percent is None or totals is None:
            continue
        score_lines.append(
            {
                "id": course.id,
                "name": course.name,
                "percent": round(percent, 1),
                "earned": totals[0],
                "possible": totals[1],
                "ink": subject_ink(course.id),
                "fill": subject_fill(course.id),
            }
        )

    course_pages = {}
    for course in snapshot.courses:
        percent = course_score_percent(snapshot, course.id)
        totals = course_score_totals(snapshot, course.id)
        upcoming_items = [
            pack_deadline(item)
            for item in upcoming(snapshot, 21)
            if item.course_id == course.id and not deadline_is_finished(snapshot, item)
        ]
        results = []
        for title, label, due, aid in course_result_rows(snapshot, course.id):
            results.append(
                {
                    "title": title,
                    "label": label,
                    "due": format_dt(due, with_time=False) if due else "No due date",
                    "assignment_id": aid,
                }
            )
        course_pages[course.id] = {
            "percent": None if percent is None else round(percent, 1),
            "fraction": (
                f"{_trim(totals[0])}/{_trim(totals[1])}" if totals else ""
            ),
            "upcoming": upcoming_items,
            "grades": results,
        }

    home_due = [
        pack_deadline(item)
        for item in upcoming(snapshot, 7)
        if not deadline_is_finished(snapshot, item)
    ]
    home_grades = [pack_grade(grade) for grade in recent_grades(snapshot, 8)[:5]]
    calendar = [pack_deadline(item) for item in snapshot.deadlines if item.when]

    return {
        "user_name": snapshot.user_name,
        "fetched_at": format_dt(snapshot.fetched_at) if snapshot.fetched_at else "Not yet refreshed",
        "has_snapshot": bool(snapshot.courses or snapshot.assignments),
        "page_size": int(settings.get("list_page_size") or 10),
        "hide_calendar_events": bool(settings.get("hide_calendar_events")),
        "deadline_colors": {
            "overdue": deadline_color("overdue"),
            "today": deadline_color("today"),
            "soon": deadline_color("soon"),
            "week": deadline_color("week"),
            "later": deadline_color("later"),
        },
        "courses": courses,
        "assignments": assignments,
        "graded": [pack_grade(grade) for grade in graded],
        "pending": [pack_grade(grade) for grade in pending],
        "score_lines": score_lines,
        "course_pages": course_pages,
        "home_due": home_due,
        "home_grades": home_grades,
        "calendar": calendar,
        "content_count": len(snapshot.content_nodes),
        "errors": snapshot.errors,
    }


def _trim(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"
