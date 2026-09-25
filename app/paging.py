"""Split long on-screen lists into pages."""

from __future__ import annotations

PAGE_SIZES = (10, 20, 50)
DEFAULT_PAGE_SIZE = 10


def normalize_page_size(value: object) -> int:
    try:
        size = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_PAGE_SIZE
    return size if size in PAGE_SIZES else DEFAULT_PAGE_SIZE


def page_of(items: list, page: int, size: int) -> tuple[list, int, int, int, int]:
    """Return the items on this page, plus page index, page count, start offset, and total."""
    size = normalize_page_size(size)
    total = len(items)
    page_count = max(1, (total + size - 1) // size) if total else 1
    current = max(0, min(int(page or 0), page_count - 1))
    start = current * size
    return items[start : start + size], current, page_count, start, total
