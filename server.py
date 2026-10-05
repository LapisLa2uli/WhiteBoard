"""WhiteBoard UI bridge. Standard library only."""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlparse

import data

data.install()
ROOT = data.resource_root()

from blackboard.store import _page_opener, _ui_font, load_settings, update_settings
from crawl import progress, start_login, start_refresh, cancel_job
from present import build_state, load_snapshot

from app.palette import DEADLINE_ROWS, apply_palette, normalize_hex
from app.google_calendar import (
    GoogleCalendarError,
    load_account,
    events_for_sync,
    remember_client,
    sign_in,
    sign_out,
    sync_account,
    sync_policy,
)

STATIC = ROOT / "static"
ASSETS = ROOT / "assets"

_google = {"status": "", "busy": False}
_google_lock = threading.Lock()


def _state() -> dict:
    status = str(progress.get("google") or _google.get("status") or "")
    payload = build_state(google_status=status, include_content=False, course_id="")
    payload["google_busy"] = bool(_google.get("busy"))
    payload["job"] = {
        "busy": bool(progress.get("busy")),
        "kind": progress.get("kind") or "",
        "message": progress.get("message") or "",
        "percent": progress.get("percent") or 0,
        "error": progress.get("error") or "",
    }
    return payload


_INACTIVITY = {"all", "1w", "1m", "3m", "6m", "1y"}


def _apply_course_filters(settings: dict, body: dict) -> None:
    if "inactivity" in body:
        key = str(body.get("inactivity") or "all")
        if key in _INACTIVITY:
            settings["inactivity"] = key
    if "hide_filtered_assignments" in body:
        settings["hide_filtered_assignments"] = bool(body.get("hide_filtered_assignments"))
    if "load_filter_courses_only" in body:
        settings["load_filter_courses_only"] = bool(body.get("load_filter_courses_only"))
    if "active_custom_filter" in body:
        settings["active_custom_filter"] = str(body.get("active_custom_filter") or "")
    delete_id = str(body.get("delete_custom_filter") or "")
    if delete_id:
        settings["custom_filters"] = [
            item
            for item in (settings.get("custom_filters") or [])
            if not (isinstance(item, dict) and str(item.get("id") or "") == delete_id)
        ]
        if str(settings.get("active_custom_filter") or "") == delete_id:
            settings["active_custom_filter"] = ""
    added = body.get("add_custom_filter")
    if isinstance(added, dict):
        name = str(added.get("name") or "").strip()
        ids = [str(item) for item in (added.get("course_ids") or []) if item]
        if name and ids:
            item = {"id": uuid.uuid4().hex[:10], "name": name, "course_ids": ids}
            filters = [
                row for row in (settings.get("custom_filters") or []) if isinstance(row, dict)
            ]
            filters.append(item)
            settings["custom_filters"] = filters
            settings["active_custom_filter"] = item["id"]
    if "assignment_history" in body:
        mode = str(body.get("assignment_history") or "off")
        settings["assignment_history"] = (
            mode if mode in {"off", "1w", "1m", "3m", "6m", "1y", "date"} else "off"
        )
    if "assignment_history_date" in body:
        raw = str(body.get("assignment_history_date") or "").strip()
        settings["assignment_history_date"] = raw if len(raw) == 10 else ""
    if settings.get("load_filter_courses_only"):
        _sync_load_course_ids(settings)


def _sync_load_course_ids(settings: dict) -> None:
    from app.filters import visible_course_ids

    active_id = str(settings.get("active_custom_filter") or "")
    custom = next(
        (
            item
            for item in (settings.get("custom_filters") or [])
            if isinstance(item, dict) and str(item.get("id") or "") == active_id
        ),
        None,
    )
    settings["load_course_ids"] = sorted(
        visible_course_ids(
            load_snapshot(),
            inactivity=str(settings.get("inactivity") or "all"),
            custom_filter=custom,
        )
    )


def _settings_patch(settings: dict) -> dict:
    from present import _custom_filters, _history_mode, _inactivity_key

    try:
        page_size = int(settings.get("list_page_size") or 10)
    except (TypeError, ValueError):
        page_size = 10
    return {
        "inactivity": _inactivity_key(settings),
        "custom_filters": _custom_filters(settings),
        "active_custom_filter": str(settings.get("active_custom_filter") or ""),
        "hide_filtered_assignments": bool(settings.get("hide_filtered_assignments")),
        "load_filter_courses_only": bool(settings.get("load_filter_courses_only")),
        "assignment_history": _history_mode(settings),
        "assignment_history_date": str(settings.get("assignment_history_date") or ""),
        "page_size": page_size if page_size in (10, 20, 50) else 10,
        "hide_calendar_events": bool(settings.get("hide_calendar_events")),
        "contents_view_mode": settings.get("contents_view_mode") or "tree",
        "google_sync_enabled": bool(settings.get("google_sync_enabled")),
        "ui_font": _ui_font(settings.get("ui_font")),
        "sidebar_collapsed": bool(settings.get("sidebar_collapsed")),
        "motion_effects": bool(settings.get("motion_effects")),
        "favorite_courses": list(settings.get("favorite_courses") or []),
        "page_opener": _page_opener(settings.get("page_opener")),
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            self._json(_state())
            return
        if parsed.path == "/api/progress":
            self._json(_progress_payload())
            return
        if parsed.path == "/logo.png":
            logo = STATIC / "logo.png"
            self._file(logo if logo.is_file() else ASSETS / "logo.png")
            return
        self._file(STATIC / _leaf_name(unquote(parsed.path), "index.html"))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {}
        if parsed.path == "/api/open":
            self._json({"ok": True})
            return
        if parsed.path == "/api/settings":
            self._json(self._save_settings(body))
            return
        if parsed.path == "/api/google/signin":
            self._json(self._google_signin(body))
            return
        if parsed.path == "/api/google/sync":
            self._json(self._google_sync(body))
            return
        if parsed.path == "/api/google/signout":
            self._json(self._google_signout())
            return
        if parsed.path == "/api/login":
            self._json(start_login(
                str(body.get("username") or ""),
                str(body.get("password") or ""),
                str(body.get("base_url") or ""),
            ))
            return
        if parsed.path == "/api/refresh":
            self._json(start_refresh())
            return
        self._json({"ok": False}, status=404)

    def log_message(self, fmt: str, *args) -> None:
        return

    def _save_settings(self, body: dict) -> dict:
        def edit(settings: dict) -> None:
            self._edit_settings(settings, body)

        settings = update_settings(edit)
        colors_changed = any(
            key in body
            for key in (
                "deadline_color",
                "reset_deadline_colors",
                "course_color",
                "reset_course_color",
                "reset_course_colors",
            )
        )
        if colors_changed:
            return _state()
        return {"patch": _settings_patch(settings)}

    def _edit_settings(self, settings: dict, body: dict) -> None:
        for key in ("sidebar_collapsed", "motion_effects"):
            if key in body: settings[key] = bool(body[key])
        if "favorite_courses" in body and isinstance(body["favorite_courses"], list):
            settings["favorite_courses"] = [str(x) for x in body["favorite_courses"]][:200]
        if "list_page_size" in body:
            try:
                size = int(body.get("list_page_size") or 10)
            except (TypeError, ValueError):
                size = 10
            settings["list_page_size"] = size if size in (10, 20, 50) else 10
        if "hide_calendar_events" in body:
            settings["hide_calendar_events"] = bool(body.get("hide_calendar_events"))
        if "contents_view_mode" in body:
            mode = str(body.get("contents_view_mode") or "tree")
            settings["contents_view_mode"] = (
                mode if mode in {"tree", "folder", "columns"} else "tree"
            )
        if "google_sync_enabled" in body:
            settings["google_sync_enabled"] = bool(body.get("google_sync_enabled"))
        if "ui_font" in body:
            settings["ui_font"] = _ui_font(body.get("ui_font"))
        if "page_opener" in body:
            settings["page_opener"] = _page_opener(body.get("page_opener"))
        allowed = {name for name, _label, _color in DEADLINE_ROWS}
        if body.get("reset_deadline_colors"):
            settings["deadline_colors"] = {}
        deadline = body.get("deadline_color") or {}
        if isinstance(deadline, dict):
            key = str(deadline.get("key") or "")
            color = normalize_hex(deadline.get("color"))
            if key in allowed and color:
                colors = dict(settings.get("deadline_colors") or {})
                colors[key] = color
                settings["deadline_colors"] = colors
        if body.get("reset_course_colors"):
            settings["course_colors"] = {}
        reset_course = str(body.get("reset_course_color") or "")
        if reset_course:
            colors = dict(settings.get("course_colors") or {})
            colors.pop(reset_course, None)
            settings["course_colors"] = colors
        course = body.get("course_color") or {}
        if isinstance(course, dict):
            course_id = str(course.get("id") or "").strip()
            color = normalize_hex(course.get("color"))
            if course_id and color:
                colors = dict(settings.get("course_colors") or {})
                colors[course_id] = color
                settings["course_colors"] = colors
        _apply_course_filters(settings, body)
        apply_palette(settings)

    def _google_signin(self, body: dict) -> dict:
        with _google_lock:
            if _google["busy"]:
                return _state()
            _google["busy"] = True
            _google["status"] = "Waiting for Google sign-in in your browser…"
        client_id, client_secret = _google_client()

        def work() -> None:
            try:
                account = sign_in(client_id, client_secret)

                def edit(settings: dict) -> None:
                    settings["google_sync_enabled"] = True

                update_settings(edit)
                who = account.get("email") or "Google"
                _run_sync(client_id, client_secret, status=f"Signed in as {who}.")
            except GoogleCalendarError as exc:
                _google["status"] = str(exc)
            except Exception as exc:
                _google["status"] = str(exc) or "Google sign-in failed."
            finally:
                _google["busy"] = False

        threading.Thread(target=work, daemon=True, name="google-sign-in").start()
        return _state()

    def _google_sync(self, body: dict) -> dict:
        with _google_lock:
            if _google["busy"]:
                return _state()
            _google["busy"] = True
            _google["status"] = "Updating Google Calendar…"
        client_id, client_secret = _google_client()

        def work() -> None:
            try:
                remember_client(client_id, client_secret)
                _run_sync(client_id, client_secret)
            finally:
                _google["busy"] = False

        threading.Thread(target=work, daemon=True, name="google-sync").start()
        return _state()

    def _google_signout(self) -> dict:
        sign_out()

        def edit(settings: dict) -> None:
            settings["google_sync_enabled"] = False

        update_settings(edit)
        _google["status"] = "Signed out of Google."
        _google["busy"] = False
        return _state()

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: Path) -> None:
        resolved = _inside(path, STATIC, ASSETS)
        if resolved is None or not resolved.is_file():
            self.send_error(404)
            return
        data = resolved.read_bytes()
        mime = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _google_client() -> tuple[str, str]:
    from app.google_calendar import builtin_google_client

    return builtin_google_client()


def _run_sync(client_id: str, client_secret: str, status: str = "") -> None:
    remember_client(client_id, client_secret)
    settings = load_settings()
    snapshot = load_snapshot()
    try:
        events = events_for_sync(
            snapshot,
            base_url=str(settings.get("base_url") or ""),
            hide_other=bool(settings.get("hide_calendar_events")),
        )
        _account, message = sync_account(load_account(), events, **sync_policy(snapshot, settings))
        _google["status"] = status or message
    except GoogleCalendarError as exc:
        _google["status"] = str(exc)
    except Exception as exc:
        _google["status"] = str(exc) or "Google Calendar sync failed."


def _progress_payload() -> dict:
    counts = progress.get("counts") if isinstance(progress.get("counts"), dict) else {}
    return {
        "id": progress.get("id", ""),
        "stage": progress.get("stage", ""),
        "revision": progress.get("revision", 0),
        "timings": dict(progress.get("timings") or {}),
        "cancelled": progress.get("cancelled", False),
        "busy": bool(progress.get("busy")),
        "kind": progress.get("kind") or "",
        "message": progress.get("message") or "",
        "percent": progress.get("percent") or 0,
        "error": progress.get("error") or "",
        "detail": progress.get("detail") or "",
        "log": list(progress.get("log") or [])[-8:],
        "counts": {
            "courses": int(counts.get("courses") or 0),
            "folders": int(counts.get("folders") or 0),
            "files": int(counts.get("files") or 0),
        },
    }


def _open_page(body: dict) -> dict:
    import host

    target, title = _launch_target(body)
    if not target:
        return {"ok": False, "message": "This assignment has no Blackboard page."}
    choice = _page_opener(load_settings().get("page_opener"))
    return _dispatch_open(choice, target, title, start=_start_browser, builtin=host.open_document)


def _dispatch_open(choice: str, target: str, title: str, *, start, builtin) -> dict:
    """Open in Chrome or Edge, and use the built-in window when that cannot start."""
    external = choice in {"system", "edge", "chrome"} and target.lower().startswith(("http://", "https://"))
    try:
        if external and start(choice, target):
            return {"ok": True, "url": target, "opened_with": choice}
    except (OSError, RuntimeError):
        pass
    builtin(target, title)
    if not external:
        return {"ok": True, "url": target, "opened_with": "builtin"}
    name = "Google Chrome" if choice == "chrome" else "Microsoft Edge"
    return {
        "ok": True,
        "url": target,
        "opened_with": "builtin",
        "fallback": True,
        "message": f"{name} could not open the page, so it opened in WhiteBoard.",
    }


def _browser_executable(kind: str):
    import os
    import shutil
    if sys.platform != "win32":
        return None
    import winreg

    name = {"edge": "msedge.exe", "chrome": "chrome.exe"}.get(kind)
    if not name:
        return None
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{name}") as key:
                raw, _typ = winreg.QueryValueEx(key, "")
        except OSError:
            continue
        path = Path(str(raw).strip().strip('"'))
        if path.is_file():
            return path
    local = os.environ.get("LOCALAPPDATA", "")
    program = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    program_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    if kind == "edge":
        candidates = [
            Path(program_x86) / "Microsoft" / "Edge" / "Application" / name,
            Path(program) / "Microsoft" / "Edge" / "Application" / name,
            Path(local) / "Microsoft" / "Edge" / "Application" / name,
        ]
    else:
        candidates = [
            Path(program) / "Google" / "Chrome" / "Application" / name,
            Path(program_x86) / "Google" / "Chrome" / "Application" / name,
            Path(local) / "Google" / "Chrome" / "Application" / name,
        ]
    for path in candidates:
        if path.is_file():
            return path
    found = shutil.which(name)
    if found and Path(found).is_file():
        return Path(found)
    return None


def _start_browser(kind: str, url: str) -> bool:
    import subprocess
    import time

    if kind == "system":
        import webbrowser
        return bool(webbrowser.open(url))
    if sys.platform == "darwin":
        name = {"chrome": "Google Chrome", "edge": "Microsoft Edge"}.get(kind)
        return bool(name) and subprocess.run(["/usr/bin/open", "-a", name, url], capture_output=True, timeout=10).returncode == 0
    exe = _browser_executable(kind)
    if exe is None:
        return False
    flags = 0x08000000 | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        proc = subprocess.Popen(
            [str(exe), url],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=flags,
        )
    except OSError:
        return False
    time.sleep(0.35)
    return proc.poll() in (None, 0)


def _launch_target(body: dict) -> tuple[str, str]:
    from blackboard.api import (
        _ids_from_launch_url,
        _is_deep_work_url,
        _match_content_by_title,
        browser_open_url,
        content_id_for_work,
        work_launch_url,
    )
    from present import load_snapshot

    settings = load_settings()
    base = str(settings.get("base_url") or "")
    snapshot = load_snapshot()
    item_id = str(body.get("id") or "")
    explicit = str(body.get("url") or "")
    title = str(body.get("title") or "")
    assignment = snapshot.assignment_by_id(item_id) if item_id else None
    if assignment is None and explicit:
        assignment = next((item for item in snapshot.assignments if item.blackboard_url == explicit), None)
    deadline = None
    if assignment is None and item_id:
        deadline = next(
            (item for item in snapshot.deadlines if item.id == item_id or item.assignment_id == item_id),
            None,
        )
    if assignment is not None:
        title = title or assignment.title
        explicit = explicit or assignment.blackboard_url
        course_id = assignment.course_id
        handler = assignment.content_handler
        item_id = assignment.id
    elif deadline is not None:
        title = title or deadline.title
        explicit = explicit or deadline.blackboard_url
        course_id = deadline.course_id
        handler = deadline.content_handler
    else:
        course_id = ""
        handler = ""
    content_id = content_id_for_work(
        snapshot,
        assignment=assignment,
        deadline=deadline,
        item_id=item_id,
        explicit=explicit,
    )
    target = work_launch_url(
        base,
        item_id=item_id,
        course_id=course_id,
        content_id=content_id,
        explicit=explicit,
        handler=handler,
        title=title,
    )
    if title and course_id and not _is_deep_work_url(target, base):
        node = _match_content_by_title(snapshot.content_nodes, course_id, title)
        found = ""
        found_handler = handler
        if isinstance(node, dict):
            found = str(node.get("id") or "")
            found_handler = str((node.get("contentHandler") or {}).get("id") or handler)
        if found:
            target = work_launch_url(
                base,
                item_id=item_id,
                course_id=course_id,
                content_id=found,
                explicit=explicit,
                handler=found_handler,
                title=title,
            )
            content_id = found or content_id
            handler = found_handler or handler
    if not handler:
        url_content, url_course = _ids_from_launch_url(explicit or target)
        node_id = url_content or content_id
        if node_id:
            node = next((item for item in snapshot.content_nodes if item.id == node_id), None)
            if node is not None:
                handler = node.handler or handler
                course_id = course_id or node.course_id
                content_id = content_id or node.id
    target = browser_open_url(
        base,
        target,
        course_id=course_id,
        content_id=content_id,
        handler=handler,
    )
    return target, title or "Blackboard"


def _remember(settings: dict, name: str, items: list, *, add: bool) -> None:
    raw = [item for item in (settings.get(name) or []) if item]
    if add:
        known = set()
        for item in raw:
            if isinstance(item, dict) and item.get("id"):
                known.add(str(item["id"]))
        for item in items:
            if item.id in known:
                continue
            row = {"id": item.id, "course_id": item.course_id, "title": item.title}
            if name == "marked_submitted_assignments":
                row["submitted_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            raw.append(row)
            known.add(item.id)
    else:
        drop_ids = {item.id for item in items}
        drop_tokens = {f"{item.course_id}::{item.title.lower()}" for item in items}
        kept = []
        for item in raw:
            if isinstance(item, str):
                if item in drop_ids or item in drop_tokens:
                    continue
            elif isinstance(item, dict):
                token = f"{item.get('course_id') or ''}::{str(item.get('title') or '').strip().lower()}"
                if str(item.get("id") or "") in drop_ids or token in drop_tokens:
                    continue
            kept.append(item)
        raw = kept
    settings[name] = raw


def _assignment_update(item, marked: set[str], ignored_keys: set[str]) -> dict:
    from app.status import effective
    return effective(item, marked, ignored_keys)


def _not_due(when) -> bool:
    from present import _as_utc

    if when is None:
        return True
    return _as_utc(when) > datetime.now(timezone.utc)


def _apply_assignment_action(settings: dict, snapshot, action: str, wanted: set[str]) -> list[dict]:
    from present import _item_flagged, _setting_keys, _submitted_ts

    chosen = [item for item in snapshot.assignments if item.id in wanted]
    if action == "submitted":
        _remember(settings, "marked_submitted_assignments", chosen, add=True)
    elif action == "unsubmit":
        _remember(settings, "marked_submitted_assignments", chosen, add=False)
    elif action == "ignore":
        _remember(settings, "ignored_assignments", chosen, add=True)
    elif action == "restore":
        _remember(settings, "ignored_assignments", chosen, add=False)
    elif action == "undo_not_due":
        marked = _setting_keys(settings, "marked_submitted_assignments")
        by_assignment = {item.id: item for item in snapshot.assignments}
        pending = []
        seen: set[str] = set()
        extras = [item for item in snapshot.deadlines if item.id not in by_assignment]
        for item in list(snapshot.assignments) + extras:
            if item.id in seen or not _item_flagged(item, marked):
                continue
            seen.add(item.id)
            when = getattr(item, "due_at", None) or getattr(item, "when", None)
            if _not_due(when):
                pending.append(item)
        chosen = pending
        _remember(settings, "marked_submitted_assignments", chosen, add=False)
    else:
        raise RuntimeError("That action is not available.")
    marked = _setting_keys(settings, "marked_submitted_assignments")
    ignored_keys = _setting_keys(settings, "ignored_assignments")
    by_id = {item.id: item for item in snapshot.assignments}
    updates = []
    seen_ids: set[str] = set()
    for item in chosen:
        if item.id in seen_ids:
            continue
        seen_ids.add(item.id)
        assignment = by_id.get(item.id)
        if assignment is not None:
            update = _assignment_update(assignment, marked, ignored_keys)
            update["submitted_ts"] = (
                _submitted_ts(settings, assignment) if update.get("status") == "submitted" else 0
            )
            updates.append(update)
        else:
            updates.append({"id": item.id, "status": "todo", "manual": False, "ignored": False, "submitted_ts": 0})
    return updates


def _assignment_action(body: dict) -> dict:
    action = str(body.get("action") or "")
    wanted = {str(item) for item in (body.get("ids") or []) if str(item)}
    snapshot = load_snapshot()
    updates: list[dict] = []

    def edit(settings: dict) -> None:
        nonlocal updates
        updates = _apply_assignment_action(settings, snapshot, action, wanted)

    update_settings(edit)
    return {"updates": updates}


_ZIP_FILE_LIMIT = 10
_ZIP_BYTE_LIMIT = 10 * 1024 * 1024


def _real_download(node) -> bool:
    path = str(getattr(node, "download_path", "") or "").strip()
    if not path:
        return False
    lowered = path.lower()
    if "cmd=view" in lowered or "listcontent.jsp" in lowered or "/ultra/" in lowered:
        return False
    return True


def _descendant_nodes(folder, nodes: list) -> list:
    children = [
        node
        for node in nodes
        if node.course_id == folder.course_id and (node.parent_id or "") == folder.id
    ]
    found = []
    for child in children:
        if child.kind == "folder":
            found.extend(_descendant_nodes(child, nodes))
        else:
            found.append(child)
    return found


def _zip_is_large(files: list) -> bool:
    total = sum(int(getattr(node, "size_bytes", 0) or 0) for node in files)
    return len(files) > _ZIP_FILE_LIMIT or total > _ZIP_BYTE_LIMIT


def _download_filename(node) -> str:
    raw = node.filename or node.display_name() or "download"
    name = _leaf_name(_safe_name(raw), "download")
    ext = str(getattr(node, "extension", "") or "").lstrip(".").lower()
    if ext and not name.lower().endswith(f".{ext}"):
        name = f"{name}.{ext}"
    return _leaf_name(name, "download")


def _zip_entry_name(folder, node, by_id: dict) -> str:
    parts = [_download_filename(node)]
    parent = node.parent_id or ""
    seen: set[str] = set()
    while parent and parent != folder.id and parent not in seen:
        seen.add(parent)
        parent_node = by_id.get(parent)
        if parent_node is None:
            break
        parts.append(parent_node.display_name())
        parent = parent_node.parent_id or ""
    safe = [_leaf_name(_safe_name(part), "file") for part in reversed(parts)]
    return "/".join(part for part in safe if part not in {".", ".."})


def _zip_progress(name: str, percent: float, *, large: bool, zip_name: str, done: bool = False, phase: str) -> None:
    _download_progress(name, percent, track="main", phase=phase)
    if large:
        _download_progress(name, percent, done=done, track=zip_name, phase=phase)


def _write_folder_zip(session, downloads: Path, folder, files: list, by_id: dict, problems: list) -> str:
    zip_name = _leaf_name(_safe_name(folder.display_name()), "folder") + ".zip"
    if not files:
        raise OSError(f"{folder.display_name()} has no downloadable files.")
    dest = _inside(_unique_path(downloads / zip_name), downloads)
    if dest is None:
        raise OSError("Could not create the zip in Downloads.")
    large = _zip_is_large(files)
    total = max(len(files), 1)
    used = set()
    dest = _reserve_path(dest)
    temporary = dest.with_name(dest.name + '.' + uuid.uuid4().hex + '.part')
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for index, node in enumerate(files):
                session._check_cancelled()
                entry = _zip_entry_name(folder, node, by_id)
                if entry in used:
                    entry = f"{index}-{entry}"
                used.add(entry)
                _zip_progress(node.display_name(), index / total, large=large, zip_name=zip_name, phase="Downloading")
                with archive.open(entry, 'w', force_zip64=True) as output:
                    session.download_to(node.download_path, output)
        os.replace(temporary, dest)
    except BaseException:
        temporary.unlink(missing_ok=True)
        dest.unlink(missing_ok=True)
        raise
    _zip_progress(zip_name, 1, large=large, zip_name=zip_name, done=large, phase="Downloading")
    return dest.name


def _download_files(body: dict) -> dict:
    from crawl import progress as job
    from present import load_snapshot
    from session import WebSession

    if job.get("busy"):
        return {"ok": False, "message": "Wait until refresh finishes, then download."}
    wanted = {str(item) for item in (body.get("ids") or []) if str(item)}
    folder_ids = [str(item) for item in (body.get("folders") or []) if str(item)]
    snapshot = load_snapshot()
    files = []
    seen: set[str] = set()
    nodes = list(snapshot.content_nodes)
    by_id = {node.id: node for node in nodes}
    zip_jobs = []
    covered: set[str] = set()
    for folder_id in folder_ids:
        folder = by_id.get(folder_id)
        if folder is None or folder.kind != "folder":
            continue
        packed = _descendant_nodes(folder, nodes)
        if not packed:
            continue
        zip_jobs.append((folder, packed))
        covered.update(node.id for node in packed)
    for node_id in wanted:
        node = by_id.get(node_id)
        if node is None or node.id in seen or node.id in covered:
            continue
        if node.kind == "folder":
            packed = _descendant_nodes(node, nodes)
            if packed:
                zip_jobs.append((node, packed))
                covered.update(item.id for item in packed)
            continue
        target = node.download_path or node.open_url
        if not target:
            continue
        files.append(node)
        seen.add(node.id)
    loose = [node for node in files if _real_download(node)]
    hidden = [node for node in files if not _real_download(node)]
    if not loose and not hidden and not zip_jobs:
        return {"ok": False, "message": "Selected items have no downloadable file."}
    from blackboard.api import embedded_download_nodes
    from blackboard.store import load_settings

    settings = load_settings()
    base = str(settings.get("base_url") or "https://shs.blackboardchina.cn")
    _download_progress("files", 0.02, track="main", phase="Preparing")
    session = WebSession(base)
    session.cancel_event = _download_cancel
    try:
        session.prepare()
    except Exception as exc:
        _download_progress("files", 1, done=True, track="main", phase="Downloading")
        return {"ok": False, "message": str(exc) or "Sign in, then try the download again."}
    folder_dir = Path.home() / "Downloads"
    folder_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    errors: list[str] = []
    zip_names: list[str] = []
    try:
        if hidden:
            _download_progress("files", 0.08, track="main", phase="Finding files")
            loose.extend(embedded_download_nodes(session, hidden, base))
        resolved_jobs = []
        for folder, packed in zip_jobs:
            _download_progress(folder.display_name(), 0.08, track="main", phase="Finding files")
            members = [node for node in packed if _real_download(node)]
            members.extend(
                embedded_download_nodes(
                    session,
                    [node for node in packed if not _real_download(node)],
                    base,
                )
            )
            resolved_jobs.append((folder, members))
        for folder, packed in resolved_jobs:
            try:
                zip_names.append(
                    _write_folder_zip(session, folder_dir, folder, packed, by_id, errors)
                )
                saved += 1
            except Exception as exc:
                errors.append(f"{folder.display_name()}: {exc}")
        total = max(len(loose), 1)
        for index, node in enumerate(loose):
            session._check_cancelled()
            name = _download_filename(node)
            _download_progress(name, index / total, track="main")
            dest = _inside(_unique_path(folder_dir / name), folder_dir)
            if dest is None:
                errors.append(f"{name}: invalid file name")
                continue
            try:
                dest = _reserve_path(dest)
                temporary = dest.with_name(dest.name + "." + uuid.uuid4().hex + ".part")
                try:
                    with temporary.open("xb") as output:
                        session.download_to(node.download_path, output)
                    os.replace(temporary, dest)
                except BaseException:
                    temporary.unlink(missing_ok=True)
                    dest.unlink(missing_ok=True)
                    raise
                saved += 1
            except Exception as exc:
                errors.append(f"{name}: {exc}")
            _download_progress(
                name,
                (index + 1) / total,
                done=False,
                track="main",
            )
    finally:
        import host

        host.set_title("WhiteBoard")
        _download_progress("files", 1, done=True, track="main", phase="Downloading")
    if not saved:
        return {
            "ok": False,
            "message": errors[0] if errors else "Selected items have no downloadable file.",
        }
    if errors:
        return {"ok": True, "message": f"Saved {saved} file(s). Some failed: {errors[0]}"}
    if zip_names and not files and saved == 1:
        return {"ok": True, "message": f"Saved {zip_names[0]} to Downloads."}
    if saved == 1 and files and not zip_names:
        return {"ok": True, "message": f"Saved {files[0].display_name()} to Downloads."}
    return {"ok": True, "message": f"Saved {saved} item(s) to Downloads."}


def _download_progress(
    name: str, percent: float, *, done: bool = False, track: str = "", phase: str = ""
) -> None:
    import host

    host.post_page(
        json.dumps(
            {
                "event": "download",
                "name": name,
                "percent": max(0.0, min(1.0, percent)),
                "done": done,
                "id": track,
                "phase": phase,
            }
        )
    )


def _leaf_name(raw: str, default: str) -> str:
    """File name only. Directory parts from a request cannot choose another folder."""
    name = os.path.basename((raw or "").replace("\\", "/")).strip()
    if not name or name in {".", ".."} or "\x00" in name:
        return default
    return name


def _inside(path: Path, *roots: Path) -> Path | None:
    try:
        resolved = path.resolve()
    except OSError:
        return None
    for root in roots:
        try:
            base = root.resolve()
        except OSError:
            continue
        if resolved == base or base in resolved.parents:
            return resolved
    return None


def _safe_name(name: str) -> str:
    import re

    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name or "").strip() or "download"
    return cleaned[:180]


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for number in __import__("itertools").count(2):
        candidate = path.with_name(f"{stem} ({number}){suffix}")
        if not candidate.exists():
            return candidate


def _reserve_path(path):
    while True:
        candidate = _unique_path(path)
        try:
            with candidate.open("xb"):
                pass
            return candidate
        except FileExistsError:
            continue


_download_lock = threading.Lock()
_download_cancel = threading.Event()

def handle(path: str, body: dict | None = None) -> dict:
    """Answer one window request. Nothing listens on a network port."""
    payload = body if isinstance(body, dict) else {}
    route = str(path or "").split("?", 1)[0]
    if route == "/api/download/cancel":
        _download_cancel.set()
        return {"ok": True}
    if route in {"/api/login", "/api/refresh", "/api/logout"} and _download_lock.locked():
        raise RuntimeError("Cancel the download or wait for it to finish first.")
    if route == "/api/content":
        result = build_state(include_content=True, course_id="")
        return {"content_nodes": result["content_nodes"], "content_loaded": result["content_loaded"],
                "files_indexed": result["files_indexed"], "content_indexing": bool(progress.get("busy")) and not result["files_indexed"],
                "revision": result["revision"]}
    if route == "/api/course":
        result = build_state(include_content=False, course_id=str(payload.get("id") or ""))
        return {"course_pages": result["course_pages"]}
    if route == "/api/google/status":
        account = load_account()
        return {"google_busy": bool(_google.get("busy")), "google": {"signed_in": bool(account.get("refresh_token")), "email": str(account.get("email") or ""), "sync_enabled": bool(load_settings().get("google_sync_enabled")), "status": str(_google.get("status") or "")}}
    if route == "/api/logout":
        if _google.get("busy"):
            raise RuntimeError("Wait for Google sync to finish before signing out.")
        from accounts import logout
        logout(bool(payload.get("keep_offline")))
        return _state()
    if route == "/api/state":
        return _state()
    if route == "/api/cancel":
        return cancel_job(str(payload.get("id") or ""))
    if route == "/api/progress":
        return _progress_payload()
    blank = Handler.__new__(Handler)
    if route == "/api/settings":
        return blank._save_settings(payload)
    if route == "/api/google/signin":
        return blank._google_signin(payload)
    if route == "/api/google/sync":
        return blank._google_sync(payload)
    if route == "/api/google/signout":
        return blank._google_signout()
    if route == "/api/login":
        return start_login(
            str(payload.get("username") or ""),
            str(payload.get("password") or ""),
            str(payload.get("base_url") or ""),
            interactive=bool(payload.get("interactive")),
        )
    if route == "/api/refresh":
        return start_refresh()
    if route == "/api/open":
        return _open_page(payload)
    if route == "/api/assignments":
        return _assignment_action(payload)
    if route == "/api/download":
        if not _download_lock.acquire(blocking=False):
            raise RuntimeError("A download is already running.")
        _download_cancel.clear()
        try:
            return _download_files(payload)
        finally:
            _download_lock.release()
    raise RuntimeError("That action is not available.")


def serve(_port: int = 0) -> None:
    """WhiteBoard does not listen on a port. Open the window instead."""
    from run import main

    main()


if __name__ == "__main__":
    from run import main

    main()
