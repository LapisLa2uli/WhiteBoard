from __future__ import annotations

import asyncio
import re
import sys
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from blackboard.api import content_id_for_work, work_launch_url
from blackboard.auth import (
    AuthExpiredError,
    DEFAULT_BASE_URL,
    BlackboardSession,
    SESSION_EXPIRED_MESSAGE,
    is_auth_error,
    resolve_url,
)
from blackboard.store import Store, load_settings, save_settings

from app.filters import INACTIVITY_OPTIONS, sidebar_courses, visible_course_ids
from app.navigation import TOP_LEVEL, is_detail_route

if TYPE_CHECKING:
    import flet as ft


class AppController:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.session: BlackboardSession | None = None
        self.store = Store()
        self.route = "/login"
        self.stack: list[str] = []
        self.login_status = "idle"
        self.login_message = ""
        self.loading_progress = 0.0
        self.loading_message = ""
        self.loading_kind = ""
        self.loading_return_route = ""
        self.loading_bar = None
        self.loading_label = None
        self.loading_percent = None
        self.grades_graded_expanded = True
        self.grades_pending_expanded = True
        self.busy = False
        self.calendar_days = 14
        self.assignment_filter = "all"
        self.assignment_query = ""
        self.course_query = ""
        self.settings = load_settings()
        self.course_list_column = None
        self.assignment_list_column = None
        self.assignment_toolbar_column = None
        self.assignment_list_forced_status = None
        self.assignment_select_mode = False
        self.selected_assignment_ids: set[str] = set()
        self.login_username = str(self.settings.get("username") or "")
        self._login_password = ""
        self._lock = threading.Lock()
        self._login_gen = 0
        self._ui_thread: threading.Thread | None = None
        self.countdown_targets: list[tuple[Any, Any]] = []
        self._countdown_gen = 0
        self.contents_expanded: set[str] = set()
        self.contents_selected: set[str] = set()
        self.contents_path: list[str] = []
        self.contents_status = ""
        self.contents_busy = False
        self.shortcut_status = ""
        self.file_picker = None
        self._shortcut_prompt_shown = False

    @property
    def base_url(self) -> str:
        return str(self.settings.get("base_url") or DEFAULT_BASE_URL).rstrip("/")

    @base_url.setter
    def base_url(self, value: str) -> None:
        self.settings["base_url"] = value.rstrip("/")
        save_settings(self.settings)

    @property
    def inactivity(self) -> str:
        value = str(self.settings.get("inactivity") or "all")
        allowed = {key for key, _label in INACTIVITY_OPTIONS}
        return value if value in allowed else "all"

    @property
    def custom_filters(self) -> list[dict[str, Any]]:
        raw = self.settings.get("custom_filters") or []
        return [item for item in raw if isinstance(item, dict)]

    @property
    def active_custom_filter(self) -> dict[str, Any] | None:
        active_id = str(self.settings.get("active_custom_filter") or "")
        return next((item for item in self.custom_filters if item.get("id") == active_id), None)

    def persist(self) -> None:
        self.settings.pop("password", None)
        save_settings(self.settings)

    @property
    def contents_view_mode(self) -> str:
        from app.contents_nav import normalize_view_mode

        return normalize_view_mode(str(self.settings.get("contents_view_mode") or "tree"))

    def set_contents_view_mode(self, mode: str) -> None:
        from app.contents_nav import normalize_view_mode

        self.settings["contents_view_mode"] = normalize_view_mode(mode)
        self.persist()
        self.rebuild()

    def contents_goto(self, path: list[str]) -> None:
        self.contents_path = list(path)
        self.rebuild()

    def contents_go_up(self) -> None:
        if self.contents_path:
            self.contents_path = self.contents_path[:-1]
            self.rebuild()

    def contents_open(self, parent_key: str | None, child_key: str) -> None:
        from app.contents_nav import path_after_open

        self.contents_path = path_after_open(self.contents_path, parent_key, child_key)
        self.rebuild()

    def ui(self, fn) -> None:
        """Run a UI update on Flet's event loop, including from worker threads."""
        if self._ui_thread is not None and threading.current_thread() is self._ui_thread:
            fn()
            return
        try:
            loop = self.page.session.connection.loop
        except Exception:
            loop = None
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is not None and (loop is None or running is loop):
            fn()
            return

        async def coro() -> None:
            fn()

        try:
            fut = self.page.run_task(coro)
            if fut is not None:
                fut.result(timeout=8)
                return
        except Exception:
            pass
        try:
            if loop is None:
                loop = self.page.session.connection.loop
            done = threading.Event()

            def wrapped() -> None:
                try:
                    fn()
                finally:
                    done.set()

            loop.call_soon_threadsafe(wrapped)
            done.wait(timeout=8)
        except Exception:
            fn()

    def go(self, route: str, *, push: bool = False) -> None:
        if route in TOP_LEVEL and not is_detail_route(route):
            self.stack.clear()
        elif push and self.route != route:
            self.stack.append(self.route)
        self.route = route
        self.rebuild()

    def back(self) -> None:
        if self.stack:
            self.route = self.stack.pop()
        else:
            from app.navigation import top_level_of

            self.route = top_level_of(self.route)
        self.rebuild()

    def rebuild(self) -> None:
        from app.views.loading import build_loading
        from app.views.login import build_login
        from app.views.shell import build_shell

        self._sync_manual_submitted()
        self._ui_thread = threading.current_thread()
        self.reset_countdowns()

        self.page.controls.clear()
        if self.route == "/loading":
            self.page.controls.append(build_loading(self))
        elif self.route == "/login" or not self.store.signed_in:
            self.page.controls.append(build_login(self))
        else:
            self.page.controls.append(build_shell(self))
        self.page.update()
        self.ensure_countdown_ticker()
        self.maybe_prompt_shortcuts()

    def reset_countdowns(self) -> None:
        self._countdown_gen += 1
        self.countdown_targets = []

    def countdown_control(self, due_at, *, status: str = "todo") -> Any:
        import flet as ft

        from app.widgets import make_countdown_text

        if due_at is None or status not in {"todo", "late"}:
            return ft.Container(width=0, height=0)
        label = make_countdown_text(due_at)
        self.countdown_targets.append((label, due_at))
        return label

    def countdown_status(
        self,
        *,
        assignment_id: str = "",
        status: str = "",
        kind: str = "",
        title: str = "",
        course_id: str = "",
    ) -> str:
        from blackboard.api import _resolve_assignment_status, assignment_for_work

        assignment = assignment_for_work(
            self.store.snapshot,
            assignment_id=assignment_id,
            title=title,
            course_id=course_id,
        )
        if assignment is not None:
            return _resolve_assignment_status(self.store.snapshot, assignment)
        if status in {"todo", "late", "submitted"}:
            return status
        return "todo" if kind in {"assignment", "todo", "late", "test"} else "submitted"

    def ensure_countdown_ticker(self) -> None:
        gen = self._countdown_gen
        targets = list(self.countdown_targets)
        if not targets:
            return

        async def tick() -> None:
            from app.widgets import countdown_color, format_countdown

            while gen == self._countdown_gen:
                current = list(self.countdown_targets)
                if not current:
                    return
                for label, due_at in current:
                    try:
                        label.value = format_countdown(due_at)
                        label.color = countdown_color(due_at)
                        label.update()
                    except Exception:
                        continue
                now = datetime.now(timezone.utc)
                delay = 1.0 - (now.microsecond / 1_000_000)
                await asyncio.sleep(max(0.05, min(delay, 1.0)))

        try:
            self.page.run_task(tick)
        except Exception:
            return

    def start_login(self, username: str = "", password: str = "") -> None:
        if self.busy:
            return
        user = (username or self.login_username or "").strip()
        secret = password or self._login_password
        if not user or not secret:
            self.login_status = "failed"
            self.login_message = "Username and password are required."
            self.rebuild()
            return
        self.login_username = user
        self._login_password = secret
        self.settings["username"] = user
        self.persist()
        self._login_gen += 1
        gen = self._login_gen
        self.busy = True
        self._begin_loading("Signing in…", 0.04, kind="login")

        def work() -> None:
            try:
                if gen != self._login_gen:
                    return
                self._open_browser_session()
                session = self.session
                if session is None or gen != self._login_gen:
                    self._close_session()
                    return
                signed_in = session.login_with_credentials(user, secret)
                if gen != self._login_gen:
                    self._close_session()
                    return
                if not signed_in:
                    raise RuntimeError("Sign-in did not finish. Check username, password, and school URL.")
                if session.base_url != self.base_url:
                    self.base_url = session.base_url
                self._on_fetch_progress("Signed in. Loading your dashboard…", 0.12)
                session.prepare_origin()
                self.store.refresh(
                    session,
                    quick=False,
                    on_progress=self._on_fetch_progress,
                    course_ids=self.fetch_course_ids(),
                )
                self._on_fetch_progress("Ready.", 1.0)
                self.route = "/home"
                self.stack.clear()
                self.login_status = "idle"
                self.login_message = ""
                self.loading_kind = ""
            except Exception as exc:
                self.login_status = "failed"
                self.login_message = str(exc) or (
                    "Could not sign in. Check username, password, school URL, Chrome/Edge, and network."
                )
                self.route = "/login"
                self.loading_progress = 0.0
                self.loading_message = ""
                self.loading_kind = ""
                self._close_session()
            finally:
                if gen == self._login_gen:
                    self.busy = False
                    self.ui(self.rebuild)

        threading.Thread(target=work, daemon=True, name="bb-login").start()

    def cancel_login(self) -> None:
        self.cancel_loading()

    def cancel_loading(self) -> None:
        if self.loading_kind == "refresh" and self.store.signed_in:
            self._login_gen += 1
            self.busy = False
            self.route = self.loading_return_route or "/home"
            self.login_status = "idle"
            self.login_message = ""
            self.loading_progress = 0.0
            self.loading_message = ""
            self.loading_kind = ""
            self.rebuild()
            return
        self._login_gen += 1
        self.busy = False
        self._close_session()
        self.route = "/login"
        self.stack.clear()
        self.login_status = "idle"
        self.login_message = "Sign-in cancelled."
        self.loading_progress = 0.0
        self.loading_message = ""
        self.loading_kind = ""
        self.rebuild()

    def _set_login_message(self, status: str, message: str) -> None:
        self.login_status = status
        self.login_message = message

        async def coro() -> None:
            self.rebuild()

        try:
            self.page.run_task(coro)
        except Exception:
            try:
                self.page.session.connection.loop.call_soon_threadsafe(self.rebuild)
            except Exception:
                pass

    def _begin_loading(self, message: str, progress: float, *, kind: str = "login") -> None:
        self.loading_kind = kind
        self.route = "/loading"
        self.login_status = "loading"
        self.loading_message = message
        self.loading_progress = max(0.0, min(1.0, progress))
        self.ui(self.rebuild)

    def _on_fetch_progress(self, message: str, progress: float | None = None) -> None:
        self.loading_message = message
        if progress is not None:
            self.loading_progress = max(0.0, min(1.0, float(progress)))

        def apply() -> None:
            from app.widgets import format_loading_message

            if self.route != "/loading":
                return
            if self.loading_label is not None:
                self.loading_label.value = format_loading_message(self.loading_message)
            if self.loading_percent is not None:
                self.loading_percent.value = f"{int(round(self.loading_progress * 100))}%"
            if self.loading_bar is not None:
                self.loading_bar.value = self.loading_progress
            self.page.update()

        self.ui(apply)

    def refresh(self) -> None:
        if self.busy:
            return
        if not self.session and not self._can_relogin():
            return
        self._login_gen += 1
        gen = self._login_gen
        self.loading_return_route = self.route if self.route != "/loading" else (
            self.loading_return_route or "/home"
        )
        self.busy = True
        self._begin_loading("Refreshing from Blackboard…", 0.02, kind="refresh")

        def work() -> None:
            try:
                retried = False
                while True:
                    try:
                        self._ensure_fresh_session(force=retried)
                        if gen != self._login_gen:
                            return
                        assert self.session is not None
                        self.store.refresh(
                            self.session,
                            quick=False,
                            on_progress=self._on_fetch_progress,
                            course_ids=self.fetch_course_ids(),
                        )
                        break
                    except AuthExpiredError:
                        if retried or not self._can_relogin():
                            raise
                        retried = True
                        self._on_fetch_progress(
                            "Session expired. Signing in again…", 0.05
                        )
                if gen != self._login_gen:
                    return
                self.store.snapshot.errors.pop("refresh", None)
                self._on_fetch_progress("Ready.", 1.0)
                self.route = self.loading_return_route or "/home"
                self.login_status = "idle"
                self.login_message = ""
            except AuthExpiredError as exc:
                if gen != self._login_gen:
                    return
                self._handle_session_expired(str(exc))
            except Exception as exc:
                if gen != self._login_gen:
                    return
                if is_auth_error(exc):
                    self._handle_session_expired(SESSION_EXPIRED_MESSAGE)
                    return
                self.store.snapshot.errors["refresh"] = str(exc)
                self.route = self.loading_return_route or "/home"
            finally:
                if gen == self._login_gen:
                    self.busy = False
                    self.loading_kind = ""
                    self.ui(self.rebuild)

        threading.Thread(target=work, daemon=True, name="bb-refresh").start()

    def _can_relogin(self) -> bool:
        return bool((self.login_username or "").strip() and self._login_password)

    def _open_browser_session(self) -> BlackboardSession:
        self._close_session()
        session = BlackboardSession(
            self.base_url,
            headless=True,
            on_progress=self._on_fetch_progress,
            on_status=lambda msg: self._on_fetch_progress(msg),
        )
        self.session = session
        session.start()
        return session

    def _ensure_fresh_session(self, *, force: bool = False) -> None:
        session = self.session
        if session is None or not getattr(session, "is_open", False):
            if not self._can_relogin():
                raise AuthExpiredError(SESSION_EXPIRED_MESSAGE)
            session = self._open_browser_session()
            force = True

        if not force:
            try:
                if session.confirm_login():
                    return
            except Exception:
                if not self._can_relogin():
                    raise AuthExpiredError(SESSION_EXPIRED_MESSAGE)
                session = self._open_browser_session()

        if not self._can_relogin():
            raise AuthExpiredError(SESSION_EXPIRED_MESSAGE)
        self._on_fetch_progress("Session expired. Signing in again…", 0.06)
        signed_in = session.login_with_credentials(
            self.login_username, self._login_password
        )
        if not signed_in:
            raise AuthExpiredError(
                "Could not sign in again. Check username and password."
            )
        if session.base_url != self.base_url:
            self.base_url = session.base_url
        session.prepare_origin()

    def _handle_session_expired(self, message: str) -> None:
        self.login_status = "failed"
        self.login_message = message or SESSION_EXPIRED_MESSAGE
        self.route = "/login"
        self.stack.clear()
        self.store.signed_in = False
        self.loading_kind = ""

    def set_grades_section(self, key: str, expanded: bool) -> None:
        if key == "graded":
            self.grades_graded_expanded = bool(expanded)
        else:
            self.grades_pending_expanded = bool(expanded)

    def logout(self) -> None:
        self._close_session()
        self.store.signed_in = False
        self.store.snapshot.errors.clear()
        self.route = "/login"
        self.stack.clear()
        self.login_status = "idle"
        self.login_message = ""
        self._login_password = ""
        self.assignment_filter = "all"
        self.assignment_query = ""
        self.assignment_select_mode = False
        self.selected_assignment_ids.clear()
        self.contents_expanded.clear()
        self.contents_selected.clear()
        self.contents_path.clear()
        self.contents_status = ""
        self.course_query = ""
        self.rebuild()

    def clear_cache(self) -> None:
        self.store.clear_disk_cache()
        self.rebuild()

    def set_inactivity(self, key: str) -> None:
        self.settings["inactivity"] = key
        self._sync_load_course_ids()
        self.persist()
        if self.hide_filtered_assignments:
            self.rebuild()
        else:
            self.refresh_course_list()

    @property
    def hide_filtered_assignments(self) -> bool:
        return bool(self.settings.get("hide_filtered_assignments"))

    def set_hide_filtered_assignments(self, value: bool) -> None:
        self.settings["hide_filtered_assignments"] = bool(value)
        self.persist()
        self.rebuild()

    def set_load_filter_courses_only(self, value: bool) -> None:
        self.settings["load_filter_courses_only"] = bool(value)
        if value:
            self._sync_load_course_ids()
        self.persist()
        self.refresh_course_list()

    def visible_course_id_set(self) -> set[str]:
        return visible_course_ids(
            self.store.snapshot,
            inactivity=self.inactivity,
            custom_filter=self.active_custom_filter,
        )

    def assignment_in_active_filter(self, course_id: str) -> bool:
        if not self.hide_filtered_assignments:
            return True
        allowed = self.visible_course_id_set()
        if not allowed:
            return True
        return course_id in allowed

    def fetch_course_ids(self) -> set[str] | None:
        if not self.settings.get("load_filter_courses_only"):
            return None
        ids = {str(item) for item in (self.settings.get("load_course_ids") or []) if item}
        return ids or None

    def _sync_load_course_ids(self) -> None:
        if not self.settings.get("load_filter_courses_only"):
            return
        self.settings["load_course_ids"] = sorted(self.visible_course_id_set())

    def set_course_query(self, query: str) -> None:
        self.course_query = query
        self.refresh_course_list()

    @property
    def hide_overdue(self) -> str:
        value = str(self.settings.get("hide_overdue") or "off")
        return value if value in {"off", "1w", "1m"} else "off"

    def set_assignment_query(self, query: str) -> None:
        self.assignment_query = query
        self.refresh_assignment_list()

    def set_hide_overdue(self, key: str) -> None:
        self.settings["hide_overdue"] = key if key in {"off", "1w", "1m"} else "off"
        self.persist()
        self.refresh_assignment_list()

    def refresh_assignment_list(self) -> None:
        from app.views.assignments import assignment_list_controls, assignment_toolbar_controls

        column = self.assignment_list_column
        toolbar = self.assignment_toolbar_column
        if column is None:
            self.rebuild()
            return
        self.reset_countdowns()
        column.controls = assignment_list_controls(
            self, forced_status=self.assignment_list_forced_status
        )
        if toolbar is not None:
            toolbar.controls = assignment_toolbar_controls(
                self, forced_status=self.assignment_list_forced_status
            )
        try:
            column.update()
            if toolbar is not None:
                toolbar.update()
        except Exception:
            self.rebuild()
            return
        self.ensure_countdown_ticker()

    def ignored_assignment_keys(self) -> set[str]:
        keys: set[str] = set()
        for item in self.settings.get("ignored_assignments") or []:
            if isinstance(item, str) and item:
                keys.add(item)
            elif isinstance(item, dict):
                if item.get("id"):
                    keys.add(str(item["id"]))
                course_id = str(item.get("course_id") or "")
                title = str(item.get("title") or "").strip().lower()
                if course_id or title:
                    keys.add(f"{course_id}::{title}")
        return keys

    def is_ignored_assignment(self, assignment) -> bool:
        keys = self.ignored_assignment_keys()
        return assignment.id in keys or f"{assignment.course_id}::{assignment.title.lower()}" in keys

    def ignore_assignments(self, assignments: list) -> None:
        raw = [item for item in (self.settings.get("ignored_assignments") or []) if item]
        keys = self.ignored_assignment_keys()
        for assignment in assignments:
            token = f"{assignment.course_id}::{assignment.title.lower()}"
            if assignment.id in keys or token in keys:
                continue
            raw.append(
                {
                    "id": assignment.id,
                    "course_id": assignment.course_id,
                    "title": assignment.title,
                }
            )
            keys.add(assignment.id)
            keys.add(token)
        self.settings["ignored_assignments"] = raw
        self.selected_assignment_ids.clear()
        self.persist()
        self.refresh_assignment_list()

    def restore_assignments(self, assignments: list) -> None:
        drop_ids = {item.id for item in assignments}
        drop_tokens = {f"{item.course_id}::{item.title.lower()}" for item in assignments}
        kept = []
        for item in self.settings.get("ignored_assignments") or []:
            if isinstance(item, str):
                if item in drop_ids or item in drop_tokens:
                    continue
            elif isinstance(item, dict):
                token = f"{item.get('course_id') or ''}::{str(item.get('title') or '').strip().lower()}"
                if str(item.get("id") or "") in drop_ids or token in drop_tokens:
                    continue
            kept.append(item)
        self.settings["ignored_assignments"] = kept
        self.selected_assignment_ids.clear()
        self.persist()
        self.refresh_assignment_list()

    def marked_submitted_keys(self) -> set[str]:
        keys: set[str] = set()
        for item in self.settings.get("marked_submitted_assignments") or []:
            if isinstance(item, str) and item:
                keys.add(item)
            elif isinstance(item, dict):
                if item.get("id"):
                    keys.add(str(item["id"]))
                course_id = str(item.get("course_id") or "")
                title = str(item.get("title") or "").strip().lower()
                if course_id or title:
                    keys.add(f"{course_id}::{title}")
        return keys

    def is_marked_submitted(self, assignment) -> bool:
        keys = self.marked_submitted_keys()
        return assignment.id in keys or f"{assignment.course_id}::{assignment.title.lower()}" in keys

    def _sync_manual_submitted(self) -> None:
        from blackboard.api import _apply_assignment_status

        self.store.snapshot.manual_submitted_keys = self.marked_submitted_keys()
        _apply_assignment_status(self.store.snapshot)

    def _refresh_after_assignment_change(self) -> None:
        self._sync_manual_submitted()
        if self.assignment_list_column is None or is_detail_route(self.route):
            self.rebuild()
        else:
            self.refresh_assignment_list()

    def mark_assignments_submitted(self, assignments: list) -> None:
        raw = [item for item in (self.settings.get("marked_submitted_assignments") or []) if item]
        keys = self.marked_submitted_keys()
        for assignment in assignments:
            token = f"{assignment.course_id}::{assignment.title.lower()}"
            if assignment.id in keys or token in keys:
                continue
            raw.append(
                {
                    "id": assignment.id,
                    "course_id": assignment.course_id,
                    "title": assignment.title,
                }
            )
            keys.add(assignment.id)
            keys.add(token)
        self.settings["marked_submitted_assignments"] = raw
        self.selected_assignment_ids.clear()
        self.persist()
        self._refresh_after_assignment_change()

    def unmark_assignments_submitted(self, assignments: list) -> None:
        drop_ids = {item.id for item in assignments}
        drop_tokens = {f"{item.course_id}::{item.title.lower()}" for item in assignments}
        kept = []
        for item in self.settings.get("marked_submitted_assignments") or []:
            if isinstance(item, str):
                if item in drop_ids or item in drop_tokens:
                    continue
            elif isinstance(item, dict):
                token = f"{item.get('course_id') or ''}::{str(item.get('title') or '').strip().lower()}"
                if str(item.get("id") or "") in drop_ids or token in drop_tokens:
                    continue
            kept.append(item)
        self.settings["marked_submitted_assignments"] = kept
        for assignment in self.store.snapshot.assignments:
            token = f"{assignment.course_id}::{assignment.title.lower()}"
            if assignment.id in drop_ids or token in drop_tokens:
                if not assignment.has_attempt:
                    assignment.status = "todo"
        self.selected_assignment_ids.clear()
        self.persist()
        self._refresh_after_assignment_change()

    def mark_selected_assignments_submitted(self) -> None:
        from app.views.assignments import visible_assignments

        chosen = [
            item
            for item in visible_assignments(self, forced_status=self.assignment_list_forced_status)
            if item.id in self.selected_assignment_ids and item.status != "submitted"
        ]
        if chosen:
            self.mark_assignments_submitted(chosen)

    def toggle_assignment_select_mode(self) -> None:
        self.assignment_select_mode = not self.assignment_select_mode
        if not self.assignment_select_mode:
            self.selected_assignment_ids.clear()
        self.rebuild()

    def toggle_assignment_selected(self, assignment_id: str) -> None:
        if assignment_id in self.selected_assignment_ids:
            self.selected_assignment_ids.discard(assignment_id)
        else:
            self.selected_assignment_ids.add(assignment_id)
        self.refresh_assignment_list()

    def select_visible_assignments(self, assignment_ids: list[str]) -> None:
        self.assignment_select_mode = True
        self.selected_assignment_ids = set(assignment_ids)
        self.refresh_assignment_list()

    def ignore_selected_assignments(self) -> None:
        from app.views.assignments import visible_assignments

        chosen = [
            item
            for item in visible_assignments(self, forced_status=self.assignment_list_forced_status)
            if item.id in self.selected_assignment_ids
        ]
        if chosen:
            self.ignore_assignments(chosen)

    def restore_selected_assignments(self) -> None:
        from app.views.assignments import visible_assignments

        chosen = [
            item
            for item in visible_assignments(self, forced_status=self.assignment_list_forced_status)
            if item.id in self.selected_assignment_ids
        ]
        if chosen:
            self.restore_assignments(chosen)

    def confirm_delete_custom_filter(self, filter_id: str) -> None:
        import flet as ft

        from app import theme

        item = next((row for row in self.custom_filters if row.get("id") == filter_id), None)
        name = str((item or {}).get("name") or "this filter")

        def confirm(_e=None) -> None:
            self.page.pop_dialog()
            self.delete_custom_filter(filter_id)

        dialog = ft.AlertDialog(
            title=ft.Text("Delete filter?"),
            content=ft.Text(f'Delete "{name}"? This cannot be undone.'),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("Delete", on_click=confirm, bgcolor=theme.LATE, color="white"),
            ],
        )
        self.page.show_dialog(dialog)

    def open_work_in_blackboard(
        self, url: str = "", course_id: str = "", assignment_id: str = ""
    ) -> None:
        snapshot = self.store.snapshot
        assignment = snapshot.assignment_by_id(assignment_id) if assignment_id else None
        deadline = next(
            (item for item in snapshot.deadlines if item.id == assignment_id),
            None,
        ) if assignment_id else None
        item_id = assignment_id or (assignment.id if assignment else "")
        course_id = (
            course_id
            or (assignment.course_id if assignment else "")
            or (deadline.course_id if deadline else "")
        )
        explicit = (
            url
            or (assignment.blackboard_url if assignment else "")
            or (deadline.blackboard_url if deadline else "")
        )
        course = snapshot.course_by_id(course_id)
        if course and course_id != course.id:
            course_id = course.id
        content_id = content_id_for_work(
            snapshot,
            assignment=assignment,
            deadline=deadline,
            item_id=item_id,
            explicit=explicit,
        )
        handler = ""
        title = ""
        if assignment:
            handler = assignment.content_handler
            title = assignment.title
        elif deadline:
            handler = deadline.content_handler
            title = deadline.title
        target = work_launch_url(
            self.base_url,
            item_id=item_id,
            course_id=course_id,
            content_id=content_id,
            explicit=explicit,
            handler=handler,
            title=title,
        )
        self.open_blackboard(target)

    def toggle_custom_filter(self, filter_id: str) -> None:
        current = str(self.settings.get("active_custom_filter") or "")
        self.settings["active_custom_filter"] = "" if current == filter_id else filter_id
        self._sync_load_course_ids()
        self.persist()
        self.rebuild()

    def add_custom_filter(self, name: str, course_ids: list[str]) -> None:
        item = {
            "id": uuid.uuid4().hex[:10],
            "name": name.strip(),
            "course_ids": list(course_ids),
        }
        filters = list(self.custom_filters)
        filters.append(item)
        self.settings["custom_filters"] = filters
        self.settings["active_custom_filter"] = item["id"]
        self._sync_load_course_ids()
        self.persist()
        self.rebuild()

    def delete_custom_filter(self, filter_id: str) -> None:
        self.settings["custom_filters"] = [
            item for item in self.custom_filters if item.get("id") != filter_id
        ]
        if str(self.settings.get("active_custom_filter") or "") == filter_id:
            self.settings["active_custom_filter"] = ""
        self._sync_load_course_ids()
        self.persist()
        self.rebuild()

    def listed_courses(self):
        return sidebar_courses(
            self.store.snapshot,
            query=self.course_query,
            inactivity=self.inactivity,
            custom_filter=self.active_custom_filter,
        )

    def content_node_by_id(self, node_id: str):
        return next(
            (node for node in self.store.snapshot.content_nodes if node.id == node_id),
            None,
        )

    def maybe_prompt_shortcuts(self) -> None:
        if self._shortcut_prompt_shown or self.settings.get("shortcut_prompt_done"):
            return
        from app.shortcuts import installed_by_setup, is_packaged

        if installed_by_setup():
            return
        if not is_packaged():
            return
        show_dialog = getattr(self.page, "show_dialog", None)
        if not callable(show_dialog):
            return
        self._shortcut_prompt_shown = True
        self.show_shortcut_dialog(first_run=True)

    def show_shortcut_dialog(self, *, first_run: bool = False) -> None:
        import flet as ft

        from app import theme
        from app.shortcuts import shortcut_labels

        desktop_label, search_label = shortcut_labels()
        desktop_box = ft.Checkbox(label=desktop_label, value=True)
        search_box = ft.Checkbox(label=search_label, value=True)
        title = "Add shortcuts?" if first_run else "Create shortcuts"
        if sys.platform == "darwin":
            body = (
                "WhiteBoard can add a Desktop shortcut and place the app in your Applications "
                "folder so Spotlight can find it."
            )
        else:
            body = (
                "WhiteBoard can add a Desktop shortcut and a Start menu entry so it appears "
                "in Windows Search."
            )

        def skip(_e=None) -> None:
            self.page.pop_dialog()
            if first_run:
                self.settings["shortcut_prompt_done"] = True
                self.persist()

        def allow(_e=None) -> None:
            self.page.pop_dialog()
            self.install_app_shortcuts(
                desktop=bool(desktop_box.value),
                search=bool(search_box.value),
                remember=first_run,
            )

        dialog = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Column(
                [ft.Text(body), desktop_box, search_box],
                spacing=10,
                tight=True,
                width=420,
            ),
            actions=[
                ft.TextButton("Not now", on_click=skip),
                ft.FilledButton("Add shortcuts", on_click=allow, bgcolor=theme.ACCENT),
            ],
        )
        self.page.show_dialog(dialog)

    def install_app_shortcuts(
        self, *, desktop: bool = True, search: bool = True, remember: bool = False
    ) -> None:
        from app.shortcuts import install_shortcuts

        try:
            self.shortcut_status = install_shortcuts(desktop=desktop, search=search)
        except Exception as exc:
            self.shortcut_status = f"Could not create shortcuts: {exc}"
        if remember:
            self.settings["shortcut_prompt_done"] = True
            self.persist()
        if self.store.signed_in:
            self.rebuild()

    def toggle_content_folder(self, key: str) -> None:
        if key in self.contents_expanded:
            self.contents_expanded.discard(key)
        else:
            self.contents_expanded.add(key)
        self.rebuild()

    def toggle_content_selected(self, node_id: str) -> None:
        if node_id in self.contents_selected:
            self.contents_selected.discard(node_id)
        else:
            self.contents_selected.add(node_id)
        self.rebuild()

    def descendant_content_files(self, folder) -> list:
        from blackboard.api import content_children

        files = []
        stack = [folder]
        nodes = self.store.snapshot.content_nodes
        while stack:
            current = stack.pop()
            for child in content_children(nodes, current.course_id, current.id):
                if child.kind == "folder":
                    stack.append(child)
                else:
                    files.append(child)
        return files

    def set_folder_contents_selected(self, folder, checked: bool) -> None:
        files = self.descendant_content_files(folder)
        for node in files:
            if checked:
                self.contents_selected.add(node.id)
            else:
                self.contents_selected.discard(node.id)
        self.rebuild()

    def open_content_node(self, node) -> None:
        url = node.open_url or node.download_path
        if not url:
            self.contents_status = f"No browser link for {node.display_name()}."
            self.rebuild()
            return
        self.open_blackboard(url)

    def open_selected_contents(self) -> None:
        nodes = [
            node
            for node in self.store.snapshot.content_nodes
            if node.id in self.contents_selected
        ]
        if not nodes:
            return
        for node in nodes:
            self.open_content_node(node)

    def download_selected_contents(self) -> None:
        files = []
        seen: set[str] = set()
        for node in self.store.snapshot.content_nodes:
            if node.id in self.contents_selected and node.kind != "folder":
                if node.id not in seen:
                    files.append(node)
                    seen.add(node.id)
        if not files:
            folders = [
                node
                for node in self.store.snapshot.content_nodes
                if node.id in self.contents_selected and node.kind == "folder"
            ]
            for folder in folders:
                for child in self.descendant_content_files(folder):
                    if child.id not in seen:
                        files.append(child)
                        seen.add(child.id)
        files = [node for node in files if node.download_path or node.open_url]
        if not files:
            self.contents_status = "Selected items have no downloadable file."
            self.rebuild()
            return
        if self.contents_busy:
            return

        async def pick_and_save() -> None:
            picker = self.file_picker
            dest_dir = ""
            dest_file = ""
            try:
                if picker is None:
                    dest_dir = str(Path.home() / "Downloads")
                elif len(files) == 1:
                    dest_file = await picker.save_file(
                        dialog_title="Save file",
                        file_name=_safe_filename(files[0].display_name()),
                    )
                    if not dest_file:
                        return
                else:
                    dest_dir = await picker.get_directory_path(
                        dialog_title="Choose a folder for downloads"
                    )
                    if not dest_dir:
                        return
            except Exception as exc:
                self.contents_status = f"Could not open the save dialog: {exc}"
                self.ui(self.rebuild)
                return
            self.contents_busy = True
            self.contents_status = "Downloading…"
            self.ui(self.rebuild)
            saved = 0
            errors: list[str] = []
            try:
                for node in files:
                    name = _safe_filename(node.display_name())
                    target = Path(dest_file) if dest_file else Path(dest_dir) / name
                    self.contents_status = f"Downloading {name}…"
                    self.ui(self._update_contents_status)
                    try:
                        data = self._download_content_bytes(node)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data)
                        saved += 1
                    except Exception as exc:
                        errors.append(f"{name}: {exc}")
            finally:
                self.contents_busy = False
            if errors and not saved:
                self.contents_status = errors[0]
            elif errors:
                self.contents_status = f"Saved {saved} file(s). Some failed: {errors[0]}"
            elif dest_file:
                self.contents_status = f"Saved {files[0].display_name()}."
            else:
                self.contents_status = f"Saved {saved} file(s) to {dest_dir}."
            self.ui(self.rebuild)

        try:
            self.page.run_task(pick_and_save)
        except Exception as exc:
            self.contents_status = str(exc)
            self.rebuild()

    def _update_contents_status(self) -> None:
        self.page.update()

    def _download_content_bytes(self, node) -> bytes:
        if self.session:
            path = node.download_path or node.open_url
            if not path:
                raise RuntimeError("No download URL")
            return self.session.get_bytes(path)
        raise RuntimeError("Sign in to download course files.")

    def refresh_course_list(self) -> None:
        from app.views.course_sidebar import course_list_controls

        column = self.course_list_column
        if column is None:
            self.rebuild()
            return
        column.controls = course_list_controls(self)
        try:
            column.update()
        except Exception:
            self.rebuild()

    def show_new_filter_dialog(self) -> None:
        import flet as ft

        name_field = ft.TextField(label="Filter name", autofocus=True)
        boxes = [
            ft.Checkbox(label=course.name, value=False, data=course.id)
            for course in self.store.snapshot.courses
        ]
        error_text = ft.Text("", color="#dc2626", size=12)

        def save(_e=None) -> None:
            name = (name_field.value or "").strip()
            selected = [str(box.data) for box in boxes if box.value]
            if not name:
                error_text.value = "Give the filter a name."
                error_text.update()
                return
            if not selected:
                error_text.value = "Select at least one course for the whitelist."
                error_text.update()
                return
            self.page.pop_dialog()
            self.add_custom_filter(name, selected)

        dialog = ft.AlertDialog(
            title=ft.Text("New course filter"),
            content=ft.Column(
                [
                    ft.Text(
                        "Only the courses you check will appear in the left list when this filter is on. "
                        "Assignments and deadlines from other courses still show on Home and Calendar."
                    ),
                    name_field,
                    ft.Column(boxes, spacing=4, scroll=ft.ScrollMode.AUTO, height=220),
                    error_text,
                ],
                spacing=10,
                tight=True,
                width=380,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("Save", on_click=save),
            ],
        )
        self.page.show_dialog(dialog)

    def open_blackboard(self, url: str) -> None:
        if not url:
            return
        webbrowser.open(resolve_url(self.base_url, url))

    def _close_session(self) -> None:
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass
            self.session = None


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name or "").strip() or "download"
    return cleaned[:180]
