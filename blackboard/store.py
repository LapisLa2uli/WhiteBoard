from __future__ import annotations

import json
from pathlib import Path

from blackboard.api import fetch_snapshot
from blackboard.auth import BlackboardSession
from blackboard.models import Snapshot

DATA_DIR = Path.home() / ".blackboard_dashboard"
SNAPSHOT_PATH = DATA_DIR / "snapshot.json"
SETTINGS_PATH = DATA_DIR / "settings.json"


class Store:
    def __init__(self) -> None:
        self.snapshot = Snapshot()
        self.signed_in = False

    def refresh(
        self,
        session: BlackboardSession,
        *,
        quick: bool = False,
        on_progress: object | None = None,
        course_ids: set[str] | None = None,
    ) -> Snapshot:
        previous = session.on_progress
        if on_progress is not None:
            session.on_progress = on_progress  # type: ignore[assignment]
        try:
            snapshot = fetch_snapshot(
                session, quick=quick, course_ids=course_ids
            )
        finally:
            session.on_progress = previous
        self.snapshot = snapshot
        self.signed_in = True
        self.save_cache()
        return self.snapshot

    def load_cache(self) -> bool:
        if not SNAPSHOT_PATH.exists():
            return False
        try:
            data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
            self.snapshot = Snapshot.from_dict(data)
            self.signed_in = True
            return True
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return False

    def save_cache(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(
            json.dumps(self.snapshot.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

    def clear_disk_cache(self) -> None:
        if SNAPSHOT_PATH.exists():
            SNAPSHOT_PATH.unlink()

    def clear_cache(self) -> None:
        self.clear_disk_cache()
        self.snapshot = Snapshot()
        self.signed_in = False


def load_settings() -> dict:
    defaults = {
        "base_url": "https://shs.blackboardchina.cn",
        "username": "",
        "inactivity": "all",
        "custom_filters": [],
        "active_custom_filter": "",
        "hide_overdue": "off",
        "ignored_assignments": [],
        "hide_filtered_assignments": False,
        "load_filter_courses_only": False,
        "load_course_ids": [],
        "contents_view_mode": "tree",
        "shortcut_prompt_done": False,
    }
    if not SETTINGS_PATH.exists():
        return dict(defaults)
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(defaults)
        merged = dict(defaults)
        merged.update(data)
        if not isinstance(merged.get("custom_filters"), list):
            merged["custom_filters"] = []
        if not isinstance(merged.get("ignored_assignments"), list):
            merged["ignored_assignments"] = []
        if not isinstance(merged.get("load_course_ids"), list):
            merged["load_course_ids"] = []
        merged["hide_filtered_assignments"] = bool(merged.get("hide_filtered_assignments"))
        merged["load_filter_courses_only"] = bool(merged.get("load_filter_courses_only"))
        merged["shortcut_prompt_done"] = bool(merged.get("shortcut_prompt_done"))
        mode = str(merged.get("contents_view_mode") or "tree")
        merged["contents_view_mode"] = mode if mode in {"tree", "folder", "columns"} else "tree"
        merged["username"] = str(merged.get("username") or "")
        merged.pop("password", None)
        return merged
    except (OSError, json.JSONDecodeError):
        return dict(defaults)


def save_settings(settings: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "base_url": settings.get("base_url", "https://shs.blackboardchina.cn"),
        "username": str(settings.get("username") or ""),
        "inactivity": settings.get("inactivity", "all"),
        "custom_filters": settings.get("custom_filters") or [],
        "active_custom_filter": settings.get("active_custom_filter") or "",
        "hide_overdue": settings.get("hide_overdue") or "off",
        "ignored_assignments": settings.get("ignored_assignments") or [],
        "hide_filtered_assignments": bool(settings.get("hide_filtered_assignments")),
        "load_filter_courses_only": bool(settings.get("load_filter_courses_only")),
        "load_course_ids": [
            str(item) for item in (settings.get("load_course_ids") or []) if item
        ],
        "contents_view_mode": (
            settings.get("contents_view_mode")
            if settings.get("contents_view_mode") in {"tree", "folder", "columns"}
            else "tree"
        ),
        "shortcut_prompt_done": bool(settings.get("shortcut_prompt_done")),
    }
    SETTINGS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
