"""WhiteBoard UI bridge. Standard library only."""

from __future__ import annotations

import json
import mimetypes
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

import data

data.install()
ROOT = data.resource_root()

from blackboard.store import load_settings, update_settings
from crawl import progress, start_login, start_refresh
from present import build_state, load_snapshot

from app.palette import DEADLINE_ROWS, apply_palette, normalize_hex
from app.google_calendar import (
    GoogleCalendarError,
    events_for_sync,
    remember_client,
    sign_in,
    sign_out,
    sync_account,
)

STATIC = ROOT / "static"
ASSETS = ROOT / "assets"

_google = {"status": "", "busy": False}
_google_lock = threading.Lock()


def _state() -> dict:
    status = str(progress.get("google") or _google.get("status") or "")
    payload = build_state(google_status=status)
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
        rel = parsed.path.lstrip("/") or "index.html"
        self._file(STATIC / rel)

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
        client_id = str(body.get("client_id") or "")
        client_secret = str(body.get("client_secret") or "")
        if client_id or client_secret:
            remember_client(client_id, client_secret)
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
        client_id = str(body.get("client_id") or "")
        client_secret = str(body.get("client_secret") or "")

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
        client_id = str(body.get("client_id") or "")
        client_secret = str(body.get("client_secret") or "")

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
        resolved = path.resolve()
        allowed_roots = (STATIC.resolve(), ASSETS.resolve())
        if not path.is_file() or not any(
            resolved == root or root in resolved.parents for root in allowed_roots
        ):
            self.send_error(404)
            return
        data = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


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
        _account, message = sync_account(load_account(), events)
        _google["status"] = status or message
    except GoogleCalendarError as exc:
        _google["status"] = str(exc)
    except Exception as exc:
        _google["status"] = str(exc) or "Google Calendar sync failed."


def _progress_payload() -> dict:
    counts = progress.get("counts") if isinstance(progress.get("counts"), dict) else {}
    return {
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
    host.open_document(target, title)
    return {"ok": True, "url": target}


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
            raw.append({"id": item.id, "course_id": item.course_id, "title": item.title})
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
    from present import _item_flagged

    manual = _item_flagged(item, marked)
    ignored = _item_flagged(item, ignored_keys)
    base = item.status or "todo"
    return {
        "id": item.id,
        "status": "submitted" if base == "submitted" or manual else base,
        "manual": manual,
        "ignored": ignored,
    }


def _not_due(when) -> bool:
    from present import _as_utc

    if when is None:
        return True
    return _as_utc(when) > datetime.now(timezone.utc)


def _apply_assignment_action(settings: dict, snapshot, action: str, wanted: set[str]) -> list[dict]:
    from present import _item_flagged, _setting_keys

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
            updates.append(_assignment_update(assignment, marked, ignored_keys))
        else:
            updates.append({"id": item.id, "status": "todo", "manual": False, "ignored": False})
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


def _download_files(body: dict) -> dict:
    from crawl import progress as job
    from present import load_snapshot
    from session import WebSession

    if job.get("busy"):
        return {"ok": False, "message": "Wait until refresh finishes, then download."}
    wanted = {str(item) for item in (body.get("ids") or []) if str(item)}
    snapshot = load_snapshot()
    files = []
    seen: set[str] = set()
    nodes = list(snapshot.content_nodes)
    by_id = {node.id: node for node in nodes}
    for node_id in wanted:
        node = by_id.get(node_id)
        if node is None or node.id in seen:
            continue
        if node.kind == "folder":
            continue
        target = node.download_path or node.open_url
        if not target:
            continue
        files.append(node)
        seen.add(node.id)
    if not files:
        return {"ok": False, "message": "Selected items have no downloadable file."}
    from blackboard.store import load_settings

    settings = load_settings()
    base = str(settings.get("base_url") or "https://shs.blackboardchina.cn")
    session = WebSession(base)
    try:
        session.prepare()
    except Exception as exc:
        return {"ok": False, "message": str(exc) or "Sign in, then try the download again."}
    folder = Path.home() / "Downloads"
    folder.mkdir(parents=True, exist_ok=True)
    saved = 0
    errors: list[str] = []
    total = len(files)
    try:
        for index, node in enumerate(files):
            name = _safe_name(node.display_name())
            _download_progress(name, index / total)
            dest = _unique_path(folder / name)
            try:
                dest.write_bytes(session.get_bytes(node.download_path or node.open_url))
                saved += 1
            except Exception as exc:
                errors.append(f"{name}: {exc}")
            _download_progress(name, (index + 1) / total, done=index + 1 == total and not errors)
    finally:
        import host

        host.set_title("WhiteBoard")
    if errors and not saved:
        return {"ok": False, "message": errors[0]}
    if errors:
        return {"ok": True, "message": f"Saved {saved} file(s). Some failed: {errors[0]}"}
    if saved == 1:
        return {"ok": True, "message": f"Saved {files[0].display_name()} to Downloads."}
    return {"ok": True, "message": f"Saved {saved} files to Downloads."}


def _download_progress(name: str, percent: float, *, done: bool = False) -> None:
    import host

    host.post_page(
        json.dumps(
            {
                "event": "download",
                "name": name,
                "percent": max(0.0, min(1.0, percent)),
                "done": done,
            }
        )
    )


def _safe_name(name: str) -> str:
    import re

    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name or "").strip() or "download"
    return cleaned[:180]


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for number in range(2, 100):
        candidate = path.with_name(f"{stem} ({number}){suffix}")
        if not candidate.exists():
            return candidate
    return path


def handle(path: str, body: dict | None = None) -> dict:
    """Answer one window request. Nothing listens on a network port."""
    payload = body if isinstance(body, dict) else {}
    route = str(path or "").split("?", 1)[0]
    if route == "/api/state":
        return _state()
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
        )
    if route == "/api/refresh":
        return start_refresh()
    if route == "/api/open":
        return _open_page(payload)
    if route == "/api/assignments":
        return _assignment_action(payload)
    if route == "/api/download":
        return _download_files(payload)
    raise RuntimeError("That action is not available.")


def serve(_port: int = 0) -> None:
    """WhiteBoard does not listen on a port. Open the window instead."""
    from run import main

    main()


if __name__ == "__main__":
    from run import main

    main()
