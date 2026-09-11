from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone

import flet as ft

from app import theme


def heading(text: str, size: int = 26) -> ft.Text:
    return ft.Text(text, size=size, weight=ft.FontWeight.W_600, color=theme.TEXT)


def muted(text: str, size: int = 13, **kwargs) -> ft.Text:
    return ft.Text(text, size=size, color=theme.MUTED, **kwargs)


def format_loading_message(message: str, max_chars: int = 48) -> str:
    """Keep the progress percent visible by shortening long course names."""
    text = (message or "Loading…").strip() or "Loading…"
    if len(text) <= max_chars:
        return text
    prefix, sep, rest = text.partition(": ")
    if sep and rest:
        budget = max_chars - len(prefix) - 3
        if budget >= 8:
            return f"{prefix}: {rest[:budget].rstrip()}…"
    return text[: max_chars - 1].rstrip() + "…"


def error_banner(message: str) -> ft.Container:
    return ft.Container(
        content=ft.Text(message, color=theme.ERROR_FG, size=13),
        bgcolor=theme.ERROR_BG,
        padding=12,
        border_radius=8,
        border=ft.Border.all(1, "#fecaca"),
    )


def empty_state(message: str, on_refresh: Callable | None = None) -> ft.Container:
    actions = [muted(message)]
    if on_refresh:
        actions.append(
            ft.TextButton("Refresh", on_click=lambda e: on_refresh())
        )
    return ft.Container(
        content=ft.Column(actions, spacing=8, horizontal_alignment=ft.CrossAxisAlignment.START),
        padding=ft.Padding.symmetric(vertical=16),
    )


def card(content: ft.Control, on_click: Callable | None = None) -> ft.Container:
    return ft.Container(
        content=content,
        bgcolor=theme.CARD_BG,
        border_radius=12,
        padding=16,
        border=ft.Border.all(1, theme.BORDER),
        on_click=on_click,
        ink=on_click is not None,
    )


def subject_fill(course_id: str) -> str:
    if not course_id:
        return theme.CARD_BG
    return theme.SUBJECT_FILLS[_stable_index(course_id, len(theme.SUBJECT_FILLS))]


def subject_ink(course_id: str) -> str:
    if not course_id:
        return theme.TEXT
    return theme.SUBJECT_INKS[_stable_index(course_id, len(theme.SUBJECT_INKS))]


def deadline_border(due_at: datetime | None) -> tuple[str, float]:
    """Return (color, width) from how close the due date is."""
    if due_at is None:
        return theme.DEADLINE_NONE, 3
    hours = (_as_utc(due_at) - datetime.now(timezone.utc)).total_seconds() / 3600
    if hours < 0:
        return theme.DEADLINE_OVERDUE, 5
    if hours <= 24:
        return theme.DEADLINE_TODAY, 5
    if hours <= 72:
        return theme.DEADLINE_SOON, 4.5
    if hours <= 168:
        return theme.DEADLINE_WEEK, 4
    return theme.DEADLINE_LATER, 4


def assignment_card(
    content: ft.Control,
    *,
    course_id: str = "",
    due_at: datetime | None = None,
    on_click: Callable | None = None,
    on_double_tap: Callable | None = None,
    dimmed: bool = False,
) -> ft.Control:
    border_color, border_width = deadline_border(due_at)
    if dimmed:
        border_color, border_width = "#94a3b8", 3
    inner = ft.Container(
        content=content,
        bgcolor="#e2e8f0" if dimmed else subject_fill(course_id),
        border_radius=12,
        padding=16,
        border=ft.Border.all(border_width, border_color),
        ink=on_click is not None or on_double_tap is not None,
        opacity=0.72 if dimmed else 1,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )
    if on_click is None and on_double_tap is None:
        return inner
    return ft.GestureDetector(
        content=inner,
        on_tap=on_click,
        on_double_tap=on_double_tap,
    )


def deadline_legend() -> ft.Control:
    swatches = [
        (theme.DEADLINE_OVERDUE, "Overdue"),
        (theme.DEADLINE_TODAY, "Due today"),
        (theme.DEADLINE_SOON, "3 days"),
        (theme.DEADLINE_WEEK, "This week"),
        (theme.DEADLINE_LATER, "Later"),
    ]
    items = [
        ft.Row(
            [
                ft.Container(
                    width=14,
                    height=14,
                    border_radius=4,
                    bgcolor="white",
                    border=ft.Border.all(4, color),
                ),
                muted(label, 11),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        for color, label in swatches
    ]
    return ft.Row(
        [muted("Border: deadline", 11), *items, muted("Fill: course", 11)],
        spacing=12,
        wrap=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def course_chip(name: str, course_id: str, on_click: Callable | None = None) -> ft.Container:
    return ft.Container(
        content=ft.Text(name, size=13, weight=ft.FontWeight.W_500, color=subject_ink(course_id)),
        bgcolor=subject_fill(course_id),
        border=ft.Border.all(1, subject_ink(course_id)),
        border_radius=999,
        padding=ft.Padding.symmetric(horizontal=14, vertical=8),
        on_click=on_click,
        ink=on_click is not None,
    )


def section_title(text: str) -> ft.Text:
    return ft.Text(text, size=16, weight=ft.FontWeight.W_600, color=theme.TEXT)


def collapsible_folder(
    *,
    title: str,
    subtitle: str,
    expanded: bool,
    rows: list[ft.Control],
    empty: str,
    on_change,
    leading_icon=None,
    spacing: int = 10,
) -> ft.Control:
    children: list[ft.Control] = rows or [muted(empty)]
    return ft.Container(
        bgcolor=theme.CARD_BG,
        border=ft.Border.all(1, theme.BORDER),
        border_radius=12,
        content=ft.ExpansionTile(
            title=ft.Text(title, weight=ft.FontWeight.W_600, color=theme.TEXT),
            subtitle=ft.Text(subtitle, size=12, color=theme.MUTED),
            leading=ft.Icon(leading_icon or ft.Icons.FOLDER, color=theme.ACCENT),
            expanded=expanded,
            maintain_state=True,
            bgcolor=theme.CARD_BG,
            collapsed_bgcolor=theme.CARD_BG,
            controls_padding=ft.Padding.only(left=12, right=12, bottom=12),
            expanded_alignment=ft.Alignment.TOP_CENTER,
            expanded_cross_axis_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[ft.Column(children, spacing=spacing, tight=True)],
            on_change=on_change,
        ),
    )


def tile_expanded(event) -> bool:
    data = getattr(event, "data", None)
    if isinstance(data, bool):
        return data
    if isinstance(data, str):
        return data.lower() in {"true", "1", "yes"}
    control = getattr(event, "control", None)
    return bool(getattr(control, "expanded", True))


def status_chip(status: str) -> ft.Container:
    colors = {
        "todo": (theme.ACCENT, "#dbeafe"),
        "submitted": (theme.OK, "#d1fae5"),
        "late": (theme.LATE, "#fee2e2"),
        "test": (theme.WARN, "#ffedd5"),
        "assignment": (theme.ACCENT, "#dbeafe"),
        "other": (theme.MUTED, "#e2e8f0"),
    }
    fg, bg = colors.get(status, (theme.MUTED, "#e2e8f0"))
    return ft.Container(
        content=ft.Text(status.replace("_", " ").title(), size=11, color=fg, weight=ft.FontWeight.W_600),
        bgcolor=bg,
        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        border_radius=999,
    )


def format_countdown(due_at: datetime | None, *, now: datetime | None = None) -> str:
    """Live remaining/overdue time, accurate to the second."""
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


def countdown_color(due_at: datetime | None, *, now: datetime | None = None) -> str:
    if due_at is None:
        return theme.MUTED
    moment = now or datetime.now(timezone.utc)
    seconds = (_as_utc(due_at) - _as_utc(moment)).total_seconds()
    if seconds < 0:
        return theme.LATE
    if seconds <= 3600:
        return theme.DEADLINE_TODAY
    if seconds <= 86400:
        return theme.WARN
    return theme.ACCENT


def make_countdown_text(due_at: datetime | None) -> ft.Text:
    return ft.Text(
        format_countdown(due_at),
        size=13,
        weight=ft.FontWeight.W_700,
        color=countdown_color(due_at),
        font_family="Consolas",
        no_wrap=True,
    )


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


def file_icon(extension: str = "", *, kind: str = "file"):
    if kind == "folder":
        return ft.Icons.FOLDER
    ext = (extension or "").lower().lstrip(".")
    mapping = {
        "pdf": ft.Icons.PICTURE_AS_PDF,
        "doc": ft.Icons.DESCRIPTION,
        "docx": ft.Icons.DESCRIPTION,
        "txt": ft.Icons.DESCRIPTION,
        "rtf": ft.Icons.DESCRIPTION,
        "ppt": ft.Icons.SLIDESHOW,
        "pptx": ft.Icons.SLIDESHOW,
        "xls": ft.Icons.TABLE_CHART,
        "xlsx": ft.Icons.TABLE_CHART,
        "csv": ft.Icons.TABLE_CHART,
        "zip": ft.Icons.FOLDER,
        "rar": ft.Icons.FOLDER,
        "7z": ft.Icons.FOLDER,
        "png": ft.Icons.IMAGE,
        "jpg": ft.Icons.IMAGE,
        "jpeg": ft.Icons.IMAGE,
        "gif": ft.Icons.IMAGE,
        "webp": ft.Icons.IMAGE,
        "mp4": ft.Icons.MOVIE,
        "mov": ft.Icons.MOVIE,
        "mp3": ft.Icons.MUSIC_NOTE,
        "wav": ft.Icons.MUSIC_NOTE,
    }
    if kind == "link":
        return ft.Icons.LINK
    return mapping.get(ext, ft.Icons.INSERT_DRIVE_FILE)


def format_dt(value: datetime | None, *, with_time: bool = True) -> str:
    if value is None:
        return "No date"
    local = _as_utc(value).astimezone()
    if with_time:
        return local.strftime("%a %b %d, %H:%M")
    return local.strftime("%a %b %d")


def format_refreshed(value: datetime | None) -> str:
    if value is None:
        return "Not yet refreshed"
    local = _as_utc(value).astimezone()
    return f"Updated {local.strftime('%Y-%m-%d %H:%M')}"


def page_scroll(controls: list[ft.Control]) -> ft.Container:
    return ft.Container(
        expand=True,
        content=ft.Column(
            controls,
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
        padding=24,
        bgcolor=theme.PAGE_BG,
    )


def _stable_index(key: str, n: int) -> int:
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return int(digest, 16) % n


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
