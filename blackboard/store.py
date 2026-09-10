from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from blackboard.api import fetch_snapshot
from blackboard.auth import BlackboardSession
from blackboard.models import (
    Announcement,
    Assignment,
    ContentNode,
    Course,
    Deadline,
    Grade,
    Snapshot,
)

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
            self.snapshot = fetch_snapshot(
                session, quick=quick, course_ids=course_ids
            )
        finally:
            session.on_progress = previous
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

    def load_demo(self) -> Snapshot:
        now = datetime.now(timezone.utc)
        self.snapshot = Snapshot(
            user_name="Demo Student",
            user_id="demo",
            fetched_at=now,
            courses=[
                Course(
                    id="eng",
                    name="English Literature",
                    term="Fall 2026",
                    instructor="Ms. Chen",
                    blackboard_url="https://shs.blackboard.cn/ultra/courses/eng/outline",
                    last_activity=now - timedelta(days=2),
                ),
                Course(
                    id="math",
                    name="Mathematics",
                    term="Fall 2026",
                    instructor="Mr. Liu",
                    blackboard_url="https://shs.blackboard.cn/ultra/courses/math/outline",
                    last_activity=now - timedelta(days=20),
                ),
                Course(
                    id="chem",
                    name="Chemistry",
                    term="Fall 2026",
                    instructor="Dr. Wang",
                    blackboard_url="https://shs.blackboard.cn/ultra/courses/chem/outline",
                    last_activity=now - timedelta(days=80),
                ),
                Course(
                    id="phy",
                    name="Physics",
                    term="Fall 2026",
                    instructor="Ms. Zhou",
                    blackboard_url="https://shs.blackboard.cn/ultra/courses/phy/outline",
                    last_activity=now - timedelta(days=200),
                ),
                Course(
                    id="hist",
                    name="World History",
                    term="Fall 2025",
                    instructor="Mr. Gao",
                    blackboard_url="https://shs.blackboard.cn/ultra/courses/hist/outline",
                    last_activity=now - timedelta(days=250),
                ),
                Course(
                    id="art",
                    name="Studio Art",
                    term="Spring 2025",
                    instructor="Ms. Lin",
                    blackboard_url="https://shs.blackboard.cn/ultra/courses/art/outline",
                    last_activity=now - timedelta(days=400),
                ),
            ],
            assignments=[
                Assignment(
                    id="a1",
                    course_id="eng",
                    title="Essay 3",
                    due_at=now + timedelta(days=1, hours=6),
                    status="todo",
                    description="Compare two poems from this week's reading.",
                    blackboard_url="https://shs.blackboard.cn/ultra/courses/eng/outline",
                ),
                Assignment(
                    id="a2",
                    course_id="math",
                    title="Quiz 2",
                    due_at=now + timedelta(days=3),
                    status="todo",
                    description="Short quiz on quadratic functions.",
                    blackboard_url="https://shs.blackboard.cn/ultra/courses/math/outline",
                ),
                Assignment(
                    id="a3",
                    course_id="chem",
                    title="Lab 5 report",
                    due_at=now - timedelta(days=1),
                    status="late",
                    description="Write up titration results.",
                    blackboard_url="https://shs.blackboard.cn/ultra/courses/chem/outline",
                ),
                Assignment(
                    id="a4",
                    course_id="phy",
                    title="Problem set 1",
                    due_at=now - timedelta(days=4),
                    status="submitted",
                    description="Mechanics problems 1–12.",
                    blackboard_url="https://shs.blackboard.cn/ultra/courses/phy/outline",
                ),
            ],
            grades=[
                Grade(
                    id="g1",
                    course_id="chem",
                    title="Lab 4",
                    score="18/20",
                    posted_at=now - timedelta(days=2),
                    assignment_id="g1",
                ),
                Grade(
                    id="g2",
                    course_id="phy",
                    title="Quiz 1",
                    score="9/10",
                    posted_at=now - timedelta(days=5),
                ),
                Grade(
                    id="g4",
                    course_id="eng",
                    title="Draft workshop",
                    score="Submitted",
                ),
                Grade(
                    id="g3",
                    course_id="eng",
                    title="Reading response 2",
                    score="A-",
                    posted_at=now - timedelta(days=8),
                ),
            ],
            announcements=[
                Announcement(
                    id="n1",
                    course_id="eng",
                    title="Bring annotated poems on Monday",
                    body="We will discuss imagery in class.",
                    posted_at=now - timedelta(days=1),
                )
            ],
            deadlines=[
                Deadline(
                    id="a1",
                    title="Essay 3",
                    when=now + timedelta(days=1, hours=6),
                    course_id="eng",
                    kind="assignment",
                    assignment_id="a1",
                    blackboard_url="https://shs.blackboard.cn/ultra/courses/eng/outline",
                ),
                Deadline(
                    id="a2",
                    title="Quiz 2",
                    when=now + timedelta(days=3),
                    course_id="math",
                    kind="test",
                    assignment_id="a2",
                    blackboard_url="https://shs.blackboard.cn/ultra/courses/math/outline",
                ),
                Deadline(
                    id="a3",
                    title="Lab 5 report",
                    when=now - timedelta(days=1),
                    course_id="chem",
                    kind="assignment",
                    assignment_id="a3",
                    blackboard_url="https://shs.blackboard.cn/ultra/courses/chem/outline",
                ),
            ],
            content_nodes=[
                ContentNode(
                    id="eng-readings",
                    course_id="eng",
                    title="Readings",
                    kind="folder",
                    modified_at=now - timedelta(days=10),
                ),
                ContentNode(
                    id="eng-sonnet",
                    course_id="eng",
                    parent_id="eng-readings",
                    title="Sonnet 18",
                    filename="Sonnet 18.pdf",
                    kind="file",
                    extension="pdf",
                    mime="application/pdf",
                    size_bytes=248_320,
                    modified_at=now - timedelta(days=8),
                    open_url="https://shs.blackboard.cn/ultra/courses/eng/outline",
                    download_path="",
                ),
                ContentNode(
                    id="eng-notes",
                    course_id="eng",
                    parent_id="eng-readings",
                    title="Annotation notes",
                    filename="Annotation notes.docx",
                    kind="file",
                    extension="docx",
                    size_bytes=1_204_224,
                    modified_at=now - timedelta(days=6),
                    open_url="https://shs.blackboard.cn/ultra/courses/eng/outline",
                ),
                ContentNode(
                    id="eng-slides",
                    course_id="eng",
                    title="Slides",
                    kind="folder",
                    modified_at=now - timedelta(days=4),
                ),
                ContentNode(
                    id="eng-week1",
                    course_id="eng",
                    parent_id="eng-slides",
                    title="Week 1 imagery",
                    filename="Week 1 imagery.pptx",
                    kind="file",
                    extension="pptx",
                    size_bytes=3_412_992,
                    modified_at=now - timedelta(days=4),
                    open_url="https://shs.blackboard.cn/ultra/courses/eng/outline",
                ),
                ContentNode(
                    id="chem-labs",
                    course_id="chem",
                    title="Labs",
                    kind="folder",
                    modified_at=now - timedelta(days=12),
                ),
                ContentNode(
                    id="chem-lab4",
                    course_id="chem",
                    parent_id="chem-labs",
                    title="Lab 4 procedure",
                    filename="Lab 4 procedure.pdf",
                    kind="file",
                    extension="pdf",
                    size_bytes=512_000,
                    modified_at=now - timedelta(days=12),
                    open_url="https://shs.blackboard.cn/ultra/courses/chem/outline",
                ),
            ],
        )
        self.signed_in = True
        return self.snapshot


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
