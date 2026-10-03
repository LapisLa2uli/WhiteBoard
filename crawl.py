"""Sign in and refresh WhiteBoard's Blackboard snapshot."""

from __future__ import annotations

import threading

from blackboard.api import fetch_snapshot
from blackboard.auth import AuthExpiredError, SessionError
from blackboard.store import Store, load_settings, save_settings

from session import WebSession

_lock = threading.Lock()
progress = {
    "busy": False,
    "kind": "",
    "message": "",
    "percent": 0.0,
    "error": "",
    "google": "",
    "detail": "",
    "log": [],
    "counts": {"courses": 0, "folders": 0, "files": 0},
}
_seen_courses: set[str] = set()
_cancel = False


def _set(message: str, percent: float | None = None, *, error: str = "") -> None:
    progress["message"] = message
    if percent is not None:
        progress["percent"] = max(0.0, min(1.0, float(percent)))
    if error:
        progress["error"] = error


def _push_log(line: str) -> None:
    text = (line or "").strip()
    if not text:
        return
    log = list(progress.get("log") or [])
    if log and log[-1] == text:
        return
    log.append(text)
    progress["log"] = log[-8:]


def _on_progress(message: str, percent: float | None = None) -> None:
    if _cancel:
        raise SessionError("Cancelled.")
    _set(message, percent)
    _push_log(message)


def _on_detail(course: str, title: str, kind: str, folders: int = 0, files: int = 0) -> None:
    label = "Folder" if kind == "folder" else "File"
    line = f"{label} · {course} · {title}" if course else f"{label} · {title}"
    progress["detail"] = line
    _push_log(line)
    counts = progress.setdefault("counts", {"courses": 0, "folders": 0, "files": 0})
    if course and course not in _seen_courses:
        _seen_courses.add(course)
        counts["courses"] = int(counts.get("courses") or 0) + 1
    counts["folders"] = int(counts.get("folders") or 0) + int(folders or 0)
    counts["files"] = int(counts.get("files") or 0) + int(files or 0)


def _title(text: str) -> None:
    try:
        import host

        host.set_title(text)
    except Exception:
        return


def _save_session() -> None:
    """Keep the signed-in Blackboard session for the next launch.

    Only macOS needs this: its web host saves cookies itself, so the backend
    has to put them somewhere. Failures are ignored, costing one sign-in.
    """
    try:
        import host

        saver = getattr(host, "save_cookies", None)
        if callable(saver):
            saver()
    except Exception:
        return


def start_login(username: str, password: str, base_url: str) -> dict:
    if progress["busy"]:
        return dict(progress)
    _title("WhiteBoard — Signing in…")
    settings = load_settings()
    settings["base_url"] = (base_url or settings.get("base_url") or "").rstrip("/")
    settings["username"] = username.strip()
    save_settings(settings)
    _launch("login", username.strip(), password, settings["base_url"])
    return dict(progress)


def start_refresh() -> dict:
    if progress["busy"]:
        return dict(progress)
    _title("WhiteBoard — Refreshing…")
    settings = load_settings()
    _launch("refresh", str(settings.get("username") or ""), "", str(settings.get("base_url") or ""))
    return dict(progress)


def _launch(kind: str, username: str, password: str, base_url: str) -> None:
    global _cancel
    _cancel = False
    _seen_courses.clear()
    progress.update(
        busy=True,
        kind=kind,
        message="Starting…",
        percent=0.02,
        error="",
        detail="",
        log=["Starting…"],
        counts={"courses": 0, "folders": 0, "files": 0},
    )

    def work() -> None:
        secret = password
        try:
            _set("Preparing Blackboard…", 0.04)
            session = WebSession(base_url or "https://shs.blackboardchina.cn", on_progress=_on_progress)
            session.note_loaded = _on_detail
            if kind == "login":
                session.login(username, secret)
            else:
                session.prepare()
                if not session._me_ok():
                    raise AuthExpiredError("Your Blackboard session expired. Sign in again to refresh.")
                session.logged_in = True
            _set("Loading your dashboard…", 0.08)
            snapshot = fetch_snapshot(
                session,
                quick=False,
                include_files=True,
                course_ids=_load_course_ids(),
            )
            store = Store()
            store.snapshot = snapshot
            store.signed_in = True
            store.save_cache()
            _save_session()
            _set("Ready.", 1.0)
            _sync_google()
        except AuthExpiredError as exc:
            _set(str(exc), error=str(exc))
        except SessionError as exc:
            _set(str(exc), error=str(exc))
        except Exception as exc:
            text = str(exc) or "Refresh failed."
            _set(text, error=text)
        finally:
            secret = ""
            progress["busy"] = False
            try:
                import host

                host.return_to_app()
            except Exception:
                pass

    threading.Thread(target=work, daemon=True, name="bb-refresh").start()


def _load_course_ids() -> set[str] | None:
    settings = load_settings()
    if not settings.get("load_filter_courses_only"):
        return None
    ids = {str(item) for item in (settings.get("load_course_ids") or []) if item}
    return ids or None


def _sync_google() -> None:
    settings = load_settings()
    if not settings.get("google_sync_enabled"):
        return
    from app.google_calendar import GoogleCalendarError, events_for_sync, load_account, sync_account

    account = load_account()
    if not account.get("refresh_token"):
        return
    _set("Updating Google Calendar…", 0.98)
    try:
        snapshot = Store()
        snapshot.load_cache()
        if not snapshot.snapshot.courses and not snapshot.snapshot.deadlines:
            progress["google"] = "Sign in and refresh before syncing Google Calendar."
            return
        events = events_for_sync(
            snapshot.snapshot,
            base_url=str(settings.get("base_url") or ""),
            hide_other=bool(settings.get("hide_calendar_events")),
        )
        _account, message = sync_account(account, events)
        progress["google"] = message
    except GoogleCalendarError as exc:
        progress["google"] = str(exc)
    except Exception as exc:
        progress["google"] = str(exc) or "Google Calendar sync failed."
