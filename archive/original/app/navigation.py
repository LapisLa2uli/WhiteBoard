from __future__ import annotations

import flet as ft

SIDEBAR_ITEMS: list[tuple[str, str, object]] = [
    ("/home", "Home", ft.Icons.HOME_OUTLINED),
    ("/assignments", "Assignments", ft.Icons.ASSIGNMENT_OUTLINED),
    ("/submitted", "Submitted", ft.Icons.ASSIGNMENT_TURNED_IN_OUTLINED),
    ("/ignored", "Ignored", ft.Icons.VISIBILITY_OFF_OUTLINED),
    ("/grades", "Grades", ft.Icons.GRADE_OUTLINED),
    ("/contents", "Contents", ft.Icons.FOLDER_OUTLINED),
    ("/calendar", "Calendar", ft.Icons.CALENDAR_MONTH_OUTLINED),
    ("/settings", "Settings", ft.Icons.SETTINGS_OUTLINED),
]

TOP_LEVEL = {route for route, _label, _icon in SIDEBAR_ITEMS}


def sidebar_index(route: str) -> int:
    top = top_level_of(route)
    for index, (item_route, _label, _icon) in enumerate(SIDEBAR_ITEMS):
        if item_route == top:
            return index
    return 0


def top_level_of(route: str) -> str:
    if route.startswith("/courses"):
        return "/courses"
    if route.startswith("/assignments"):
        return "/assignments"
    if route.startswith("/submitted"):
        return "/submitted"
    if route.startswith("/contents"):
        return "/contents"
    if route in TOP_LEVEL:
        return route
    return "/home"


def is_detail_route(route: str) -> bool:
    return route.startswith("/courses/") or route.startswith("/assignments/")


def parse_id(route: str, prefix: str) -> str:
    if route.startswith(prefix):
        return route[len(prefix) :]
    return ""
