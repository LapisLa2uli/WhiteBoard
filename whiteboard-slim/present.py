"""Turn a saved Blackboard snapshot into the data the slim UI renders."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLIM = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SLIM) not in sys.path:
    sys.path.insert(0, str(SLIM))

import data

data.install()

from blackboard.api import (
    course_result_rows,
    course_score_percent,
    course_score_totals,
    deadline_is_finished,
    event_is_all_day,
    format_grade_label,
    grade_note,
    grade_page_groups,
    local_event_date,
    recent_grades,
    upcoming,
)
from blackboard.models import Snapshot
from blackboard.store import load_settings

from data import SNAPSHOT_PATH

from app.google_calendar import load_account
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


def format_size(size_bytes: int) -> str:
    if not size_bytes or size_bytes < 0:
        return "—"
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return "—"


def _setting_keys(settings: dict, name: str) -> set[str]:
    keys: set[str] = set()
    for item in settings.get(name) or []:
        if isinstance(item, str) and item:
            keys.add(item)
        elif isinstance(item, dict):
            if item.get("id"):
                keys.add(str(item["id"]))
            keys.add(
                f"{item.get('course_id') or ''}::{str(item.get('title') or '').strip().lower()}"
            )
    return keys


def _item_flagged(item, keys: set[str]) -> bool:
    token = f"{item.course_id}::{(item.title or '').strip().lower()}"
    return bool(item.id and item.id in keys) or token in keys


def build_state(snapshot: Snapshot | None = None, *, google_status: str = "") -> dict:
    settings = load_settings()
    apply_palette(settings)
    snapshot = snapshot or load_snapshot()
    courses = [
        {
            "id": course.id,
            "name": course.name,
            "term": course.term or "Course",
            "fill": subject_fill(course.id),
            "ink": subject_ink(course.id),
            "custom": course.id in (settings.get("course_colors") or {}),
        }
        for course in snapshot.courses
    ]
    course_name = {course.id: course.name for course in snapshot.courses}

    def pack_deadline(item) -> dict:
        aid = item.assignment_id or (item.id if item.kind == "assignment" else "")
        local = _as_utc(item.when).astimezone() if item.when else None
        all_day = event_is_all_day(item.when)
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
            "iso": local.isoformat(timespec="seconds") if local else "",
            "ts": int(local.timestamp()) if local else 0,
            "all_day": all_day,
            "time": "" if (not local or all_day) else local.strftime("%H:%M"),
            "kind": item.kind,
            "countdown": format_countdown(item.when),
            "border": deadline_border(item.when),
            "fill": subject_fill(item.course_id),
            "ink": subject_ink(item.course_id),
            "url": item.blackboard_url,
            "assignment_id": aid,
            "finished": deadline_is_finished(snapshot, item),
        }

    marked = _setting_keys(settings, "marked_submitted_assignments")
    ignored_keys = _setting_keys(settings, "ignored_assignments")
    assignments = []
    for item in snapshot.assignments:
        due_local = _as_utc(item.due_at).astimezone() if item.due_at else None
        manual = _item_flagged(item, marked)
        ignored = _item_flagged(item, ignored_keys)
        status = "submitted" if item.status == "submitted" or manual else item.status
        assignments.append(
            {
                "id": item.id,
                "title": item.title,
                "course_id": item.course_id,
                "course": course_name.get(item.course_id, ""),
                "when": format_dt(item.due_at),
                "status": status,
                "manual": manual,
                "ignored": ignored,
                "description": item.description,
                "countdown": format_countdown(item.due_at),
                "border": deadline_border(item.due_at),
                "fill": subject_fill(item.course_id),
                "ts": int(due_local.timestamp()) if due_local else 0,
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
        if not deadline_is_finished(snapshot, item) and not _item_flagged(item, ignored_keys)
    ]
    home_grades = [pack_grade(grade) for grade in recent_grades(snapshot, 8)[:5]]
    calendar = [pack_deadline(item) for item in snapshot.deadlines if item.when]
    account = load_account()
    content_nodes = []
    for node in snapshot.content_nodes:
        stamp = node.modified_at or node.created_at
        content_nodes.append(
            {
                "id": node.id,
                "course_id": node.course_id,
                "parent_id": node.parent_id or "",
                "name": node.display_name(),
                "kind": node.kind,
                "extension": node.extension,
                "size": node.size_bytes,
                "size_label": "—" if node.kind == "folder" else format_size(node.size_bytes),
                "date": format_dt(stamp, with_time=False) if stamp else "—",
                "url": node.open_url,
            }
        )

    return {
        "user_name": snapshot.user_name,
        "username": str(settings.get("username") or ""),
        "fetched_at": format_dt(snapshot.fetched_at) if snapshot.fetched_at else "Not yet refreshed",
        "has_snapshot": bool(snapshot.courses or snapshot.assignments),
        "page_size": int(settings.get("list_page_size") or 10),
        "hide_calendar_events": bool(settings.get("hide_calendar_events")),
        "contents_view_mode": settings.get("contents_view_mode") or "tree",
        "base_url": settings.get("base_url") or "",
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
        "content_nodes": content_nodes,
        "content_count": len(content_nodes),
        "files_indexed": bool(snapshot.files_indexed),
        "google": {
            "client_id": str(account.get("client_id") or ""),
            "client_secret": str(account.get("client_secret") or ""),
            "signed_in": bool(account.get("refresh_token")),
            "email": str(account.get("email") or ""),
            "sync_enabled": bool(settings.get("google_sync_enabled")),
            "status": google_status,
        },
        "errors": snapshot.errors,
    }


def _trim(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"
