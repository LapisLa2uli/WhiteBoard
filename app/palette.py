"""Deadline and course colors, including values chosen in Settings."""

from __future__ import annotations

import hashlib

from app import theme

DEADLINE_ROWS = (
    ("overdue", "Overdue", theme.DEADLINE_OVERDUE),
    ("today", "Due today", theme.DEADLINE_TODAY),
    ("soon", "Within 3 days", theme.DEADLINE_SOON),
    ("week", "This week", theme.DEADLINE_WEEK),
    ("later", "Later", theme.DEADLINE_LATER),
)

SWATCHES = (
    "#9f1239",
    "#ea580c",
    "#eab308",
    "#22c55e",
    "#2563eb",
    "#1d4ed8",
    "#15803d",
    "#a16207",
    "#c2410c",
    "#7e22ce",
    "#0f766e",
    "#be185d",
    "#4338ca",
    "#6d28d9",
    "#db2777",
    "#0891b2",
    "#65a30d",
    "#0f172a",
)

_deadline: dict[str, str] = {key: color for key, _label, color in DEADLINE_ROWS}
_courses: dict[str, str] = {}


def normalize_hex(value: object) -> str | None:
    text = str(value or "").strip().lower()
    if len(text) == 6 and all(char in "0123456789abcdef" for char in text):
        text = f"#{text}"
    if (
        len(text) == 7
        and text.startswith("#")
        and all(char in "0123456789abcdef" for char in text[1:])
    ):
        return text
    return None


def apply_palette(settings: dict | None) -> None:
    """Install saved colors. Missing or invalid values stay on the defaults."""
    global _deadline, _courses
    raw = (settings or {}).get("deadline_colors") if isinstance(settings, dict) else None
    colors = {key: color for key, _label, color in DEADLINE_ROWS}
    if isinstance(raw, dict):
        for key, _label, _fallback in DEADLINE_ROWS:
            parsed = normalize_hex(raw.get(key))
            if parsed:
                colors[key] = parsed
    chosen: dict[str, str] = {}
    raw_courses = (settings or {}).get("course_colors") if isinstance(settings, dict) else None
    if isinstance(raw_courses, dict):
        for course_id, value in raw_courses.items():
            parsed = normalize_hex(value)
            key = str(course_id or "").strip()
            if parsed and key:
                chosen[key] = parsed
    _deadline = colors
    _courses = chosen


def deadline_color(key: str) -> str:
    fallback = next(color for name, _label, color in DEADLINE_ROWS if name == key)
    return _deadline.get(key, fallback)


def course_color(course_id: str) -> str | None:
    return _courses.get(course_id)


def subject_ink(course_id: str) -> str:
    if not course_id:
        return theme.TEXT
    custom = _courses.get(course_id)
    if custom:
        return custom
    return theme.SUBJECT_INKS[_stable_index(course_id, len(theme.SUBJECT_INKS))]


def subject_fill(course_id: str) -> str:
    if not course_id:
        return theme.CARD_BG
    custom = _courses.get(course_id)
    if custom:
        return soften(custom)
    return theme.SUBJECT_FILLS[_stable_index(course_id, len(theme.SUBJECT_FILLS))]


def soften(hex_color: str, amount: float = 0.86) -> str:
    """Mix a strong color toward white so it can sit behind text."""
    red = int(hex_color[1:3], 16)
    green = int(hex_color[3:5], 16)
    blue = int(hex_color[5:7], 16)
    red = round(red + (255 - red) * amount)
    green = round(green + (255 - green) * amount)
    blue = round(blue + (255 - blue) * amount)
    return f"#{red:02x}{green:02x}{blue:02x}"


def _stable_index(key: str, count: int) -> int:
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return int(digest, 16) % count
