from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

AssignmentStatus = Literal["todo", "submitted", "late"]
DeadlineKind = Literal["assignment", "test", "other"]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@dataclass
class Course:
    id: str
    name: str
    term: str = ""
    instructor: str = ""
    blackboard_url: str = ""
    last_activity: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["last_activity"] = _iso(self.last_activity)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Course:
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            term=str(data.get("term", "")),
            instructor=str(data.get("instructor", "")),
            blackboard_url=str(data.get("blackboard_url", "")),
            last_activity=_parse_stored_dt(data.get("last_activity")),
        )


@dataclass
class Assignment:
    id: str
    course_id: str
    title: str
    due_at: datetime | None = None
    status: AssignmentStatus = "todo"
    blackboard_url: str = ""
    description: str = ""
    content_id: str = ""
    content_handler: str = ""
    has_attempt: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["due_at"] = _iso(self.due_at)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Assignment:
        return cls(
            id=str(data.get("id", "")),
            course_id=str(data.get("course_id", "")),
            title=str(data.get("title", "")),
            due_at=_parse_stored_dt(data.get("due_at")),
            status=data.get("status") or "todo",
            blackboard_url=str(data.get("blackboard_url", "")),
            description=str(data.get("description", "")),
            content_id=str(data.get("content_id", "")),
            content_handler=str(data.get("content_handler", "")),
            has_attempt=bool(data.get("has_attempt")),
        )


@dataclass
class Grade:
    id: str
    course_id: str
    title: str
    score: str = ""
    posted_at: datetime | None = None
    assignment_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["posted_at"] = _iso(self.posted_at)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Grade:
        return cls(
            id=str(data.get("id", "")),
            course_id=str(data.get("course_id", "")),
            title=str(data.get("title", "")),
            score=str(data.get("score", "")),
            posted_at=_parse_stored_dt(data.get("posted_at")),
            assignment_id=str(data.get("assignment_id", "")),
        )


@dataclass
class Deadline:
    id: str
    title: str
    when: datetime | None = None
    course_id: str = ""
    kind: DeadlineKind = "other"
    assignment_id: str = ""
    blackboard_url: str = ""
    content_id: str = ""
    content_handler: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["when"] = _iso(self.when)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Deadline:
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            when=_parse_stored_dt(data.get("when")),
            course_id=str(data.get("course_id", "")),
            kind=data.get("kind") or "other",
            assignment_id=str(data.get("assignment_id", "")),
            blackboard_url=str(data.get("blackboard_url", "")),
            content_id=str(data.get("content_id", "")),
            content_handler=str(data.get("content_handler", "")),
        )


@dataclass
class Announcement:
    id: str
    course_id: str
    title: str
    body: str = ""
    posted_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["posted_at"] = _iso(self.posted_at)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Announcement:
        return cls(
            id=str(data.get("id", "")),
            course_id=str(data.get("course_id", "")),
            title=str(data.get("title", "")),
            body=str(data.get("body", "")),
            posted_at=_parse_stored_dt(data.get("posted_at")),
        )


@dataclass
class ContentNode:
    id: str
    course_id: str
    parent_id: str = ""
    title: str = ""
    filename: str = ""
    kind: str = "file"
    handler: str = ""
    mime: str = ""
    extension: str = ""
    size_bytes: int = 0
    modified_at: datetime | None = None
    created_at: datetime | None = None
    open_url: str = ""
    download_path: str = ""

    def display_name(self) -> str:
        return self.filename or self.title or "Untitled"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["modified_at"] = _iso(self.modified_at)
        data["created_at"] = _iso(self.created_at)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContentNode:
        return cls(
            id=str(data.get("id", "")),
            course_id=str(data.get("course_id", "")),
            parent_id=str(data.get("parent_id", "")),
            title=str(data.get("title", "")),
            filename=str(data.get("filename", "")),
            kind=str(data.get("kind") or "file"),
            handler=str(data.get("handler", "")),
            mime=str(data.get("mime", "")),
            extension=str(data.get("extension", "")),
            size_bytes=int(data.get("size_bytes") or 0),
            modified_at=_parse_stored_dt(data.get("modified_at")),
            created_at=_parse_stored_dt(data.get("created_at")),
            open_url=str(data.get("open_url", "")),
            download_path=str(data.get("download_path", "")),
        )


@dataclass
class Snapshot:
    user_name: str = ""
    user_id: str = ""
    courses: list[Course] = field(default_factory=list)
    assignments: list[Assignment] = field(default_factory=list)
    grades: list[Grade] = field(default_factory=list)
    deadlines: list[Deadline] = field(default_factory=list)
    announcements: list[Announcement] = field(default_factory=list)
    content_nodes: list[ContentNode] = field(default_factory=list)
    fetched_at: datetime | None = None
    errors: dict[str, str] = field(default_factory=dict)
    manual_submitted_keys: set[str] = field(default_factory=set)

    def course_by_id(self, course_id: str) -> Course | None:
        return next((c for c in self.courses if c.id == course_id), None)

    def assignment_by_id(self, assignment_id: str) -> Assignment | None:
        return next((a for a in self.assignments if a.id == assignment_id), None)

    def course_name(self, course_id: str) -> str:
        course = self.course_by_id(course_id)
        return course.name if course else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_name": self.user_name,
            "user_id": self.user_id,
            "courses": [c.to_dict() for c in self.courses],
            "assignments": [a.to_dict() for a in self.assignments],
            "grades": [g.to_dict() for g in self.grades],
            "deadlines": [d.to_dict() for d in self.deadlines],
            "announcements": [a.to_dict() for a in self.announcements],
            "content_nodes": [n.to_dict() for n in self.content_nodes],
            "fetched_at": _iso(self.fetched_at),
            "errors": dict(self.errors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snapshot:
        return cls(
            user_name=str(data.get("user_name", "")),
            user_id=str(data.get("user_id", "")),
            courses=[Course.from_dict(x) for x in data.get("courses", [])],
            assignments=[Assignment.from_dict(x) for x in data.get("assignments", [])],
            grades=[Grade.from_dict(x) for x in data.get("grades", [])],
            deadlines=[Deadline.from_dict(x) for x in data.get("deadlines", [])],
            announcements=[Announcement.from_dict(x) for x in data.get("announcements", [])],
            content_nodes=[ContentNode.from_dict(x) for x in data.get("content_nodes", [])],
            fetched_at=_parse_stored_dt(data.get("fetched_at")),
            errors=dict(data.get("errors") or {}),
        )


def _parse_stored_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
