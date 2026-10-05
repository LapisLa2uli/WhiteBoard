"""Turn a saved Blackboard snapshot into the data the window renders."""

from __future__ import annotations

import html
import copy
import threading
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


_live_snapshot = None
_live_revision = 0
_state_cache = {}
_state_lock = threading.RLock()

def publish_stage(snapshot):
    global _live_snapshot, _live_revision
    with _state_lock:
        _live_snapshot = copy.deepcopy(snapshot) if snapshot is not None else None
        _live_revision += 1
        _state_cache.clear()


_snapshot_cache: dict = {"key": None, "snapshot": None}


def load_snapshot() -> Snapshot:
    if _live_snapshot is not None:
        return _live_snapshot
    from persistence import read_json, validate_snapshot
    path = data.SNAPSHOT_PATH
    if not path.exists() and path.with_name("dashboard.json").exists():
        path = path.with_name("dashboard.json")
    key = (str(path), path.stat().st_mtime_ns if path.exists() else None)
    if _snapshot_cache.get("key") == key and _snapshot_cache.get("snapshot") is not None:
        return _snapshot_cache["snapshot"]
    payload, recovery = read_json(path, {}, validate=validate_snapshot)
    try:
        snapshot = Snapshot.from_dict(payload)
    except (TypeError, ValueError, AttributeError):
        snapshot = Snapshot()
        recovery = "Saved data could not be read. Sign in to refresh it."
    if recovery:
        snapshot.errors["storage"] = recovery
    _snapshot_cache.update(key=key, snapshot=snapshot)
    return snapshot


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def format_dt(value: datetime | None, *, with_time: bool = True) -> str:
    if value is None:
        return "No date"
    local = _as_utc(value).astimezone()
    if with_time:
        return local.strftime("%a %b %d %Y, %H:%M %Z")
    return local.strftime("%a %b %d %Y")


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


from app.status import setting_keys as _setting_keys, flagged as _item_flagged, effective


def _submitted_ts(settings: dict, item) -> int:
    token = f"{item.course_id}::{(item.title or '').strip().lower()}"
    for row in settings.get("marked_submitted_assignments") or []:
        if not isinstance(row, dict):
            continue
        row_token = f"{row.get('course_id') or ''}::{str(row.get('title') or '').strip().lower()}"
        if str(row.get("id") or "") != item.id and row_token != token:
            continue
        raw = str(row.get("submitted_at") or "")
        if not raw:
            return 0
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return 0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return int(parsed.timestamp())
    return 0


def _build_state(snapshot: Snapshot | None = None, *, google_status: str = "", include_content=True, course_id=None) -> dict:
    settings = load_settings()
    apply_palette(settings)
    snapshot = snapshot or load_snapshot()
    snapshot.manual_submitted_keys = _setting_keys(settings, "marked_submitted_assignments")
    courses = [
        {
            "id": course.id,
            "name": course.name,
            "term": course.term or "Course",
            "instructor": course.instructor or "",
            "activity": int(_as_utc(course.last_activity).timestamp()) if course.last_activity else 0,
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
    history_cutoff = _history_cutoff_ts(settings)
    assignments = []
    for item in snapshot.assignments:
        due_local = _as_utc(item.due_at).astimezone() if item.due_at else None
        due_ts = int(due_local.timestamp()) if due_local else 0
        manual = _item_flagged(item, marked)
        ignored = _item_flagged(item, ignored_keys)
        status = effective(item, marked, ignored_keys)["status"]
        assignments.append(
            {
                "id": item.id,
                "title": item.title,
                "course_id": item.course_id,
                "course": course_name.get(item.course_id, ""),
                "when": format_dt(item.due_at),
                "status": status,
                "base_status": item.status or "todo",
                "manual": manual,
                "ignored": ignored,
                "description": item.description,
                "countdown": format_countdown(item.due_at),
                "border": deadline_border(item.due_at),
                "fill": subject_fill(item.course_id),
                "ts": int(due_local.timestamp()) if due_local else 0,
                "url": item.blackboard_url,
                "handler": item.content_handler,
                "submitted_ts": _submitted_ts(settings, item) if status == "submitted" else 0,
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
            "due": format_dt(grade.posted_at, with_time=False) if grade.posted_at else "Posted date unavailable",
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
    for course in (snapshot.courses if course_id is None else [c for c in snapshot.courses if c.id == course_id]):
        percent = course_score_percent(snapshot, course.id)
        totals = course_score_totals(snapshot, course.id)
        upcoming_items = [
            row
            for row in (
                pack_deadline(item)
                for item in upcoming(snapshot, 21)
                if item.course_id == course.id and not deadline_is_finished(snapshot, item)
            )
            if _kept_history(row["ts"], row.get("kind") or "", history_cutoff)
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
        row
        for row in (
            pack_deadline(item)
            for item in upcoming(snapshot, 7)
            if not deadline_is_finished(snapshot, item) and not _item_flagged(item, ignored_keys)
        )
        if _kept_history(row["ts"], row.get("kind") or "", history_cutoff)
    ]
    home_grades = [pack_grade(grade) for grade in recent_grades(snapshot, 8)[:5]]
    calendar = [
        row
        for row in (pack_deadline(item) for item in snapshot.deadlines if item.when)
        if _kept_history(row["ts"], row.get("kind") or "", history_cutoff)
    ]
    account = load_account()
    content_nodes = []
    for node in (snapshot.content_nodes if include_content else []):
        stamp = node.modified_at or node.created_at
        content_nodes.append(
            {
                "id": node.id,
                "course_id": node.course_id,
                "parent_id": node.parent_id or "",
                "name": html.unescape(node.display_name()),
                "kind": node.kind,
                "extension": node.extension,
                "size": node.size_bytes,
                "size_label": "—" if node.kind == "folder" else format_size(node.size_bytes),
                "date": format_dt(stamp, with_time=False) if stamp else "—",
                "date_ts": int(_as_utc(stamp).timestamp()) if stamp else 0,
                "url": node.open_url,
            }
        )

    return {
        "user_name": snapshot.user_name,
        "username": str(settings.get("username") or ""),
        "fetched_at": format_dt(snapshot.fetched_at) if snapshot.fetched_at else "Not yet refreshed",
        "has_snapshot": bool(snapshot.courses or snapshot.assignments),
        "page_size": int(settings.get("list_page_size") or 10),
        "ui_font": str(settings.get("ui_font") or "system"),
        "sidebar_collapsed": bool(settings.get("sidebar_collapsed")),
        "motion_effects": bool(settings.get("motion_effects")),
        "favorite_courses": list(settings.get("favorite_courses") or []),
        "offline": __import__("accounts").is_offline(),
        "page_opener": str(settings.get("page_opener") or "builtin"),
        "hide_calendar_events": bool(settings.get("hide_calendar_events")),
        "contents_view_mode": settings.get("contents_view_mode") or "tree",
        "inactivity": _inactivity_key(settings),
        "custom_filters": _custom_filters(settings),
        "active_custom_filter": str(settings.get("active_custom_filter") or ""),
        "hide_filtered_assignments": bool(settings.get("hide_filtered_assignments")),
        "load_filter_courses_only": bool(settings.get("load_filter_courses_only")),
        "assignment_history": _history_mode(settings),
        "assignment_history_date": str(settings.get("assignment_history_date") or ""),
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
        "content_count": len(snapshot.content_nodes),
        "content_loaded": include_content and bool(snapshot.files_indexed),
        "revision": _live_revision,
        "partial": _live_snapshot is not None or bool(snapshot.errors) or not snapshot.files_indexed,
        "files_indexed": bool(snapshot.files_indexed),
        "google": {
            "signed_in": bool(account.get("refresh_token")),
            "email": str(account.get("email") or ""),
            "sync_enabled": bool(settings.get("google_sync_enabled")),
            "status": google_status,
        },
        "errors": snapshot.errors,
    }


def _history_mode(settings: dict) -> str:
    value = str(settings.get("assignment_history") or "off")
    return value if value in {"off", "1w", "1m", "3m", "6m", "1y", "date"} else "off"


def _history_cutoff_ts(settings: dict) -> int:
    from blackboard.api import _history_cutoff

    cutoff = _history_cutoff(settings)
    if cutoff is None:
        return 0
    return int(cutoff.timestamp())


def _kept_history(ts: int, kind: str, cutoff: int) -> bool:
    if not cutoff or not ts or kind == "other":
        return True
    return ts >= cutoff


def _inactivity_key(settings: dict) -> str:
    value = str(settings.get("inactivity") or "all")
    return value if value in {"all", "1w", "1m", "3m", "6m", "1y"} else "all"


def _custom_filters(settings: dict) -> list[dict]:
    rows = []
    for item in settings.get("custom_filters") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        rows.append(
            {
                "id": str(item.get("id")),
                "name": str(item.get("name") or "Filter"),
                "course_ids": [str(cid) for cid in (item.get("course_ids") or []) if cid],
            }
        )
    return rows


def _trim(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def build_state(snapshot=None, *, google_status="", include_content=True, course_id=None):
    # Cache only immutable presentation output; callers receive their own copy.
    if snapshot is not None:
        return _build_state(snapshot, google_status=google_status, include_content=include_content, course_id=course_id)
    def stamp(path):
        return (str(path), path.stat().st_mtime_ns) if path.exists() else (str(path), 0)
    key = (stamp(data.SNAPSHOT_PATH), stamp(data.SNAPSHOT_PATH.with_name("dashboard.json")), stamp(data.SETTINGS_PATH), stamp(data.GOOGLE_PATH), _live_revision, int(time.time() // 60), include_content, course_id)
    with _state_lock:
        if key not in _state_cache:
            if len(_state_cache) >= 8:
                _state_cache.clear()
            _state_cache[key] = _build_state(include_content=include_content, course_id=course_id)
        result = copy.deepcopy(_state_cache[key])
    result['google']['status'] = google_status
    return result
