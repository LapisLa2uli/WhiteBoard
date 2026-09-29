"""Pure helpers for Contents tree, folder, and Miller-column views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from blackboard.api import content_children
from blackboard.models import ContentNode, Course

VIEW_MODES = ("tree", "folder", "columns")
MAX_COLUMNS = 3


@dataclass
class ExplorerItem:
    key: str
    name: str
    is_folder: bool
    is_course: bool = False
    node: ContentNode | None = None
    size_bytes: int | None = None
    modified_at: Any = None


def course_folder_key(course_id: str) -> str:
    return f"course:{course_id}"


def parse_course_key(key: str) -> str | None:
    if key.startswith("course:"):
        return key[len("course:") :]
    return None


def normalize_view_mode(value: str | None) -> str:
    mode = str(value or "tree")
    return mode if mode in VIEW_MODES else "tree"


def miller_columns(path: list[str], max_cols: int = MAX_COLUMNS) -> list[tuple[str | None, str | None]]:
    """Return (parent_key, selected_child_key) for each visible column.

    ``parent_key`` is None for the course-root listing. The left column is
    always a parent of the column to its right. At most ``max_cols`` columns
    are returned; deeper paths drop the leftmost ancestors.
    """
    n = min(max_cols, len(path) + 1)
    start = len(path) + 1 - n
    columns: list[tuple[str | None, str | None]] = []
    for offset in range(n):
        parent_index = start + offset - 1
        parent_key = None if parent_index < 0 else path[parent_index]
        selected_index = start + offset
        selected = path[selected_index] if selected_index < len(path) else None
        columns.append((parent_key, selected))
    return columns


def path_after_open(path: list[str], parent_key: str | None, child_key: str) -> list[str]:
    """Replace the trail after ``parent_key`` with the opened child folder."""
    if parent_key is None:
        return [child_key]
    if parent_key in path:
        index = path.index(parent_key)
        return path[: index + 1] + [child_key]
    return [parent_key, child_key]


def explorer_items(
    courses: Iterable[Course],
    nodes: list[ContentNode],
    parent_key: str | None,
) -> list[ExplorerItem]:
    if parent_key is None:
        return [
            ExplorerItem(
                key=course_folder_key(course.id),
                name=course.name,
                is_folder=True,
                is_course=True,
            )
            for course in courses
        ]
    course_id = parse_course_key(parent_key)
    if course_id is not None:
        children = content_children(nodes, course_id, "")
    else:
        folder = next((node for node in nodes if node.id == parent_key), None)
        if folder is None:
            return []
        children = content_children(nodes, folder.course_id, folder.id)
    items: list[ExplorerItem] = []
    for child in children:
        items.append(
            ExplorerItem(
                key=child.id,
                name=child.display_name(),
                is_folder=child.kind == "folder",
                node=child,
                size_bytes=child.size_bytes,
                modified_at=child.modified_at or child.created_at,
            )
        )
    return items
