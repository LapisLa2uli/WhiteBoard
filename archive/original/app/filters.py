"""Course list filters: inactivity windows and named whitelists."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from blackboard.models import Course, Snapshot

INACTIVITY_OPTIONS: list[tuple[str, str]] = [
    ("all", "Any activity"),
    ("1w", "Past 1 week"),
    ("1m", "Past 1 month"),
    ("3m", "Past 3 months"),
    ("6m", "Past 6 months"),
    ("1y", "Past 1 year"),
]

_INACTIVITY_DAYS = {
    "1w": 7,
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
}


def inactivity_cutoff(key: str) -> datetime | None:
    days = _INACTIVITY_DAYS.get(key)
    if not days:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


def course_last_activity(course: Course, snapshot: Snapshot) -> datetime | None:
    now = datetime.now(timezone.utc)
    times: list[datetime] = []
    if course.last_activity:
        times.append(_as_utc(course.last_activity))
    for grade in snapshot.grades:
        if grade.course_id == course.id and grade.posted_at:
            times.append(_as_utc(grade.posted_at))
    for note in snapshot.announcements:
        if note.course_id == course.id and note.posted_at:
            times.append(_as_utc(note.posted_at))
    past = [moment for moment in times if moment <= now + timedelta(hours=1)]
    return max(past) if past else None


def is_course_filtered_out(
    course: Course,
    snapshot: Snapshot,
    *,
    inactivity: str,
    custom_filter: dict[str, Any] | None,
) -> bool:
    if custom_filter:
        allowed = {str(cid) for cid in custom_filter.get("course_ids") or []}
        if course.id not in allowed:
            return True
    cutoff = inactivity_cutoff(inactivity)
    if cutoff:
        activity = course_last_activity(course, snapshot)
        if activity is not None and activity < cutoff:
            return True
    return False


def visible_course_ids(
    snapshot: Snapshot,
    *,
    inactivity: str,
    custom_filter: dict[str, Any] | None,
) -> set[str]:
    return {
        course.id
        for course in snapshot.courses
        if not is_course_filtered_out(
            course, snapshot, inactivity=inactivity, custom_filter=custom_filter
        )
    }


def sidebar_courses(
    snapshot: Snapshot,
    *,
    query: str,
    inactivity: str,
    custom_filter: dict[str, Any] | None,
) -> list[tuple[Course, bool]]:
    needle = query.strip().lower()
    rows: list[tuple[Course, bool]] = []
    for course in snapshot.courses:
        hidden = is_course_filtered_out(
            course, snapshot, inactivity=inactivity, custom_filter=custom_filter
        )
        if needle:
            haystack = f"{course.name} {course.term} {course.instructor}".lower()
            if needle in haystack:
                rows.append((course, hidden))
        elif not hidden:
            rows.append((course, False))
    return rows


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
