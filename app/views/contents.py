from __future__ import annotations

import flet as ft

from blackboard.models import ContentNode, Course

from app import theme
from app.contents_nav import ExplorerItem, explorer_items, miller_columns, parse_course_key
from app.controller import AppController
from app.widgets import (
    empty_state,
    error_banner,
    file_icon,
    format_dt,
    format_size,
    heading,
    muted,
    page_scroll,
)


def build_contents(ctrl: AppController) -> ft.Control:
    snapshot = ctrl.store.snapshot
    courses, nodes = _visible_courses_and_nodes(ctrl)
    selected_count = len(ctrl.contents_selected)
    toolbar = ft.Column(
        [
            _view_mode_toggle(ctrl),
            ft.Row(
                [
                    ft.FilledButton(
                        "Download",
                        icon=ft.Icons.DOWNLOAD,
                        disabled=not selected_count or ctrl.contents_busy,
                        on_click=lambda e: ctrl.download_selected_contents(),
                        bgcolor=theme.ACCENT,
                    ),
                    ft.OutlinedButton(
                        "Open in browser",
                        icon=ft.Icons.OPEN_IN_NEW,
                        disabled=not selected_count,
                        on_click=lambda e: ctrl.open_selected_contents(),
                    ),
                    muted(
                        f"{selected_count} selected"
                        if selected_count
                        else "Select files to download or open."
                    ),
                ],
                spacing=8,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=8,
    )

    intro = muted(
        "Course files. Metadata loads with Refresh; files download only when you choose Download."
    )
    blocks: list[ft.Control] = [heading("Contents"), intro, toolbar]
    if ctrl.contents_status:
        blocks.append(muted(ctrl.contents_status))
    if snapshot.errors.get("contents"):
        blocks.append(error_banner("Couldn't load some course contents. Try Refresh."))

    if not courses:
        blocks.append(empty_state("No courses in this filter.", ctrl.refresh))
        return page_scroll(blocks)

    mode = ctrl.contents_view_mode
    if mode == "folder":
        blocks.extend(_folder_view(ctrl, courses, nodes))
        return page_scroll(blocks)
    if mode == "columns":
        blocks.append(_breadcrumb_row(ctrl, courses, nodes))
        blocks.append(
            ft.Container(
                content=_columns_view(ctrl, courses, nodes),
                height=520,
            )
        )
        return page_scroll(blocks)

    blocks.append(_list_header())
    rows: list[ft.Control] = []
    for course in courses:
        course_key = f"course:{course.id}"
        expanded = course_key in ctrl.contents_expanded
        course_nodes = [node for node in nodes if node.course_id == course.id]
        rows.append(
            _folder_row(
                ctrl,
                key=course_key,
                name=course.name,
                depth=0,
                expanded=expanded,
                size_label="—",
                date_label="",
                is_course=True,
            )
        )
        if expanded:
            rows.extend(_tree_rows(ctrl, course_nodes, course.id, "", 1))

    if not snapshot.content_nodes:
        blocks.append(
            empty_state("No course files indexed yet. Use Refresh after signing in.", ctrl.refresh)
        )
    elif not any(node.course_id in {course.id for course in courses} for node in nodes):
        blocks.append(empty_state("No files in the visible courses.", ctrl.refresh))

    blocks.extend(rows)
    return page_scroll(blocks)


def _view_mode_toggle(ctrl: AppController) -> ft.Control:
    buttons: list[ft.Control] = []
    for mode, label in (("tree", "Tree"), ("folder", "Folder"), ("columns", "Columns")):
        selected = ctrl.contents_view_mode == mode
        if selected:
            buttons.append(
                ft.FilledButton(
                    label,
                    on_click=lambda e, value=mode: ctrl.set_contents_view_mode(value),
                    bgcolor=theme.ACCENT,
                )
            )
        else:
            buttons.append(
                ft.OutlinedButton(
                    label,
                    on_click=lambda e, value=mode: ctrl.set_contents_view_mode(value),
                )
            )
    return ft.Row(buttons, spacing=6, wrap=True)


def _visible_courses_and_nodes(
    ctrl: AppController,
) -> tuple[list[Course], list[ContentNode]]:
    courses: list[Course] = []
    for course, hidden in ctrl.listed_courses():
        if hidden and ctrl.hide_filtered_assignments:
            continue
        courses.append(course)
    nodes = [
        node
        for node in ctrl.store.snapshot.content_nodes
        if ctrl.assignment_in_active_filter(node.course_id)
    ]
    return courses, nodes


def _path_label(ctrl: AppController, courses: list[Course], nodes: list[ContentNode], key: str) -> str:
    course_id = parse_course_key(key)
    if course_id is not None:
        course = next((item for item in courses if item.id == course_id), None)
        return course.name if course else course_id
    node = next((item for item in nodes if item.id == key), None)
    return node.display_name() if node else key


def _breadcrumb_row(ctrl: AppController, courses: list[Course], nodes: list[ContentNode]) -> ft.Control:
    crumbs: list[ft.Control] = [
        ft.TextButton(
            "Courses",
            on_click=lambda e: ctrl.contents_goto([]),
        )
    ]
    for index, key in enumerate(ctrl.contents_path):
        crumbs.append(ft.Text("/", color=theme.MUTED, size=13))
        trail = list(ctrl.contents_path[: index + 1])
        crumbs.append(
            ft.TextButton(
                _path_label(ctrl, courses, nodes, key),
                on_click=lambda e, dest=trail: ctrl.contents_goto(dest),
            )
        )
    return ft.Row(
        [
            ft.IconButton(
                icon=ft.Icons.ARROW_UPWARD,
                tooltip="Up one folder",
                disabled=not ctrl.contents_path,
                on_click=lambda e: ctrl.contents_go_up(),
            ),
            *crumbs,
        ],
        spacing=0,
        wrap=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _list_header() -> ft.Control:
    return ft.Container(
        bgcolor=theme.CARD_BG,
        padding=ft.Padding.symmetric(horizontal=8, vertical=8),
        border=ft.Border.all(1, theme.BORDER),
        border_radius=8,
        content=ft.Row(
            [
                ft.Container(width=64),
                ft.Text("Name", expand=True, weight=ft.FontWeight.W_600, size=12, color=theme.MUTED),
                ft.Container(
                    content=ft.Text("Size", size=12, weight=ft.FontWeight.W_600, color=theme.MUTED),
                    width=88,
                ),
                ft.Container(
                    content=ft.Text(
                        "Date modified", size=12, weight=ft.FontWeight.W_600, color=theme.MUTED
                    ),
                    width=150,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def _folder_view(
    ctrl: AppController, courses: list[Course], nodes: list[ContentNode]
) -> list[ft.Control]:
    parent_key = ctrl.contents_path[-1] if ctrl.contents_path else None
    items = explorer_items(courses, nodes, parent_key)
    rows: list[ft.Control] = [_breadcrumb_row(ctrl, courses, nodes), _list_header()]
    if not items:
        if parent_key is None and not ctrl.store.snapshot.content_nodes:
            rows.append(
                empty_state(
                    "No course files indexed yet. Use Refresh after signing in.", ctrl.refresh
                )
            )
        else:
            rows.append(empty_state("This folder is empty."))
        return rows
    for item in items:
        rows.append(_explorer_row(ctrl, item, parent_key=parent_key, depth=0, show_meta=True))
    return rows


def _columns_view(
    ctrl: AppController, courses: list[Course], nodes: list[ContentNode]
) -> ft.Control:
    columns: list[ft.Control] = []
    specs = miller_columns(ctrl.contents_path)
    for parent_key, selected_key in specs:
        items = explorer_items(courses, nodes, parent_key)
        title = "Courses" if parent_key is None else _path_label(ctrl, courses, nodes, parent_key)
        body: list[ft.Control] = []
        if not items:
            body.append(
                ft.Container(
                    content=muted("Empty"),
                    padding=12,
                )
            )
        for item in items:
            body.append(
                _explorer_row(
                    ctrl,
                    item,
                    parent_key=parent_key,
                    depth=0,
                    show_meta=False,
                    highlighted=item.key == selected_key,
                )
            )
        columns.append(
            ft.Container(
                expand=True,
                bgcolor=theme.CARD_BG,
                border=ft.Border.all(1, theme.BORDER),
                border_radius=8,
                content=ft.Column(
                    [
                        ft.Container(
                            content=ft.Text(
                                title, size=12, weight=ft.FontWeight.W_600, color=theme.MUTED
                            ),
                            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                            border=ft.Border.only(bottom=ft.BorderSide(1, theme.BORDER)),
                        ),
                        ft.Column(body, spacing=0, scroll=ft.ScrollMode.AUTO, expand=True),
                    ],
                    spacing=0,
                    expand=True,
                ),
            )
        )
    while len(columns) < 3:
        columns.append(ft.Container(expand=True))
    return ft.Row(columns, spacing=8, expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH)


def _explorer_row(
    ctrl: AppController,
    item: ExplorerItem,
    *,
    parent_key: str | None,
    depth: int,
    show_meta: bool,
    highlighted: bool = False,
) -> ft.Control:
    selected = bool(item.node) and (
        item.node.id in ctrl.contents_selected
        if not item.is_folder
        else _folder_selected(ctrl, item.node)
    )
    date_label = "—"
    if item.modified_at:
        date_label = format_dt(item.modified_at, with_time=False)
    icon = ft.Icons.FOLDER if item.is_folder else file_icon(
        item.node.extension if item.node else "",
        kind=item.node.kind if item.node else "file",
    )
    icon_color = "#ca8a04" if item.is_folder else (
        theme.ACCENT if not item.node or item.node.kind != "link" else theme.MUTED
    )

    def on_open(_e=None, current=item) -> None:
        if current.is_folder:
            ctrl.contents_open(parent_key, current.key)

    def on_check(event, current=item) -> None:
        if current.node is None:
            return
        if current.is_folder:
            _on_folder_check(ctrl, current.node, bool(event.control.value))
        else:
            ctrl.toggle_content_selected(current.node.id)

    name = ft.Container(
        expand=True,
        on_click=on_open if item.is_folder else None,
        ink=item.is_folder,
        content=ft.Text(
            item.name,
            size=13,
            weight=ft.FontWeight.W_600 if item.is_folder else ft.FontWeight.W_400,
            no_wrap=True,
        ),
    )
    cells: list[ft.Control] = [
        ft.Checkbox(
            value=selected,
            on_change=on_check,
            disabled=item.node is None,
        )
        if not item.is_course
        else ft.Container(width=32),
        ft.Container(
            content=ft.Icon(icon, size=18, color=icon_color),
            on_click=on_open if item.is_folder else None,
        ),
        name,
    ]
    if show_meta:
        cells.extend(
            [
                ft.Container(
                    content=ft.Text(
                        "—" if item.is_folder else format_size(item.size_bytes),
                        size=12,
                        color=theme.MUTED,
                    ),
                    width=88,
                ),
                ft.Container(content=ft.Text(date_label, size=12, color=theme.MUTED), width=150),
            ]
        )
    if item.node is not None and not item.is_folder:
        cells.append(
            ft.IconButton(
                icon=ft.Icons.OPEN_IN_NEW,
                icon_size=16,
                tooltip="Open in browser",
                on_click=lambda e, node=item.node: ctrl.open_content_node(node),
            )
        )
    bg = "#dbeafe" if highlighted else ("#eff6ff" if selected and not item.is_folder else (
        theme.CARD_BG if depth % 2 == 0 else "#f8fafc"
    ))
    return ft.Container(
        bgcolor=bg,
        padding=ft.Padding.only(left=8 + depth * 16, right=8, top=4, bottom=4),
        border=ft.Border.only(bottom=ft.BorderSide(1, theme.BORDER)),
        content=ft.Row(cells, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    )


def _tree_rows(
    ctrl: AppController,
    nodes: list[ContentNode],
    course_id: str,
    parent_id: str,
    depth: int,
) -> list[ft.Control]:
    from blackboard.api import content_children

    rows: list[ft.Control] = []
    for node in content_children(nodes, course_id, parent_id):
        if node.kind == "folder":
            key = node.id
            expanded = key in ctrl.contents_expanded
            rows.append(
                _folder_row(
                    ctrl,
                    key=key,
                    name=node.display_name(),
                    depth=depth,
                    expanded=expanded,
                    size_label="—",
                    date_label=format_dt(node.modified_at or node.created_at, with_time=False)
                    if (node.modified_at or node.created_at)
                    else "—",
                    node=node,
                )
            )
            if expanded:
                rows.extend(_tree_rows(ctrl, nodes, course_id, node.id, depth + 1))
        else:
            rows.append(_file_row(ctrl, node, depth))
    return rows


def _folder_row(
    ctrl: AppController,
    *,
    key: str,
    name: str,
    depth: int,
    expanded: bool,
    size_label: str,
    date_label: str,
    is_course: bool = False,
    node: ContentNode | None = None,
) -> ft.Control:
    chevron = ft.Icons.EXPAND_MORE if expanded else ft.Icons.CHEVRON_RIGHT
    icon = ft.Icons.FOLDER_OPEN if expanded else ft.Icons.FOLDER
    return ft.Container(
        bgcolor=theme.CARD_BG if depth % 2 == 0 else "#f8fafc",
        padding=ft.Padding.only(left=8 + depth * 16, right=8, top=4, bottom=4),
        border=ft.Border.only(bottom=ft.BorderSide(1, theme.BORDER)),
        content=ft.Row(
            [
                ft.IconButton(
                    icon=chevron,
                    icon_size=16,
                    width=32,
                    height=32,
                    on_click=lambda e, folder=key: ctrl.toggle_content_folder(folder),
                ),
                ft.Checkbox(
                    value=node is not None and _folder_selected(ctrl, node),
                    on_change=lambda e, item=node: _on_folder_check(ctrl, item, e.control.value)
                    if item
                    else None,
                    disabled=node is None,
                )
                if not is_course
                else ft.Container(width=32),
                ft.Icon(icon, size=18, color="#ca8a04"),
                ft.Text(name, expand=True, weight=ft.FontWeight.W_600, size=13, no_wrap=True),
                ft.Container(content=ft.Text(size_label, size=12, color=theme.MUTED), width=88),
                ft.Container(content=ft.Text(date_label or "—", size=12, color=theme.MUTED), width=150),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def _file_row(ctrl: AppController, node: ContentNode, depth: int) -> ft.Control:
    selected = node.id in ctrl.contents_selected
    date_label = format_dt(node.modified_at or node.created_at, with_time=False)
    if not (node.modified_at or node.created_at):
        date_label = "—"
    return ft.Container(
        bgcolor="#eff6ff" if selected else (theme.CARD_BG if depth % 2 == 0 else "#f8fafc"),
        padding=ft.Padding.only(left=8 + depth * 16, right=8, top=4, bottom=4),
        border=ft.Border.only(bottom=ft.BorderSide(1, theme.BORDER)),
        content=ft.Row(
            [
                ft.Container(width=32),
                ft.Checkbox(
                    value=selected,
                    on_change=lambda e, nid=node.id: ctrl.toggle_content_selected(nid),
                ),
                ft.Icon(
                    file_icon(node.extension, kind=node.kind),
                    size=18,
                    color=theme.ACCENT if node.kind != "link" else theme.MUTED,
                ),
                ft.Text(node.display_name(), expand=True, size=13, no_wrap=True),
                ft.Container(
                    content=ft.Text(format_size(node.size_bytes), size=12, color=theme.MUTED),
                    width=88,
                ),
                ft.Container(content=ft.Text(date_label, size=12, color=theme.MUTED), width=150),
                ft.IconButton(
                    icon=ft.Icons.OPEN_IN_NEW,
                    icon_size=16,
                    tooltip="Open in browser",
                    on_click=lambda e, item=node: ctrl.open_content_node(item),
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def _folder_selected(ctrl: AppController, folder: ContentNode) -> bool:
    files = ctrl.descendant_content_files(folder)
    return bool(files) and all(node.id in ctrl.contents_selected for node in files)


def _on_folder_check(ctrl: AppController, folder: ContentNode, checked: bool) -> None:
    ctrl.set_folder_contents_selected(folder, bool(checked))
