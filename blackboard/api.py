"""Fetch and normalize Ultra / Learn JSON after a signed-in session."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Literal

from urllib.parse import parse_qs, quote, urlencode, urlparse

from blackboard.auth import (
    ApiRequestError,
    AuthExpiredError,
    BlackboardSession,
    SESSION_EXPIRED_MESSAGE,
    is_auth_error,
    resolve_url,
)
from blackboard.models import (
    Announcement,
    Assignment,
    AssignmentStatus,
    ContentNode,
    Course,
    Deadline,
    DeadlineKind,
    Grade,
    Snapshot,
)

USER_PATHS = (
    "/learn/api/v1/users/me",
    "/learn/api/public/v1/users/me",
    "/learn/api/v1/utilities/self",
)

MEMBERSHIP_PATHS = (
    "/learn/api/v1/users/{user_id}/memberships?expand=course",
    "/learn/api/public/v1/users/{user_id}/courses",
    "/learn/api/v1/users/me/memberships?expand=course",
    "/learn/api/v1/users/me/courses",
    "/learn/api/ultra/course/list",
)

CALENDAR_PATHS = (
    "/learn/api/v1/calendars/dueDateCalendarItems",
    "/learn/api/v1/calendars/calendarItems",
    "/learn/api/public/v1/calendars/items",
    "/learn/api/v1/users/{user_id}/dueDateCalendarItems",
    "/learn/api/v1/calendars/items",
)

GRADE_STREAM_PATHS = (
    "/learn/api/v1/users/{user_id}/grades",
    "/learn/api/public/v1/users/{user_id}/grades",
    "/learn/api/v1/users/me/grades",
    "/learn/api/public/v1/users/me/grades",
    "/learn/api/v1/streams/ultra?type=GRADE",
)

COURSE_GRADE_PATHS = (
    "/learn/api/v1/courses/{course_id}/gradebook/grades?userId={user_id}",
    "/learn/api/v1/users/{user_id}/courses/{course_id}/gradebook/grades",
    "/learn/api/public/v2/courses/{course_id}/gradebook/columns",
    "/learn/api/public/v1/courses/{course_id}/gradebook/columns",
    "/learn/api/v1/users/{user_id}/courses/{course_id}/gradebook/items",
)

ANNOUNCEMENT_PATHS = (
    "/learn/api/v1/courses/{course_id}/announcements",
    "/learn/api/public/v1/courses/{course_id}/announcements",
)

COURSE_COLUMN_PATHS = (
    "/learn/api/public/v2/courses/{course_id}/gradebook/columns",
    "/learn/api/public/v1/courses/{course_id}/gradebook/columns",
    "/learn/api/v1/courses/{course_id}/gradebook/columns",
)

COURSE_CONTENT_PATHS = (
    "/learn/api/public/v1/courses/{course_id}/contents?recursive=true",
    "/learn/api/public/v1/courses/{course_id}/contents",
    "/learn/api/v1/courses/{course_id}/contents",
)

COURSE_CONTENT_CHILDREN = (
    "/learn/api/public/v1/courses/{course_id}/contents/{content_id}/children",
    "/learn/api/v1/courses/{course_id}/contents/{content_id}/children",
)

COURSE_ATTACHMENT_PATHS = (
    "/learn/api/public/v1/courses/{course_id}/contents/{content_id}/attachments",
    "/learn/api/v1/courses/{course_id}/contents/{content_id}/attachments",
)

_HTML_LINK_RE = re.compile(
    r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)

_BB_PK = re.compile(r"^_\d+_\d+$")


class SectionError(Exception):
    pass


def fetch_snapshot(
    session: BlackboardSession,
    *,
    quick: bool = False,
    course_ids: set[str] | None = None,
    include_files: bool = False,
) -> Snapshot:
    snapshot = Snapshot(fetched_at=datetime.now(timezone.utc))
    session._tell("Loading your profile…", 0.04)

    user = _try_paths(session, USER_PATHS[:2], snapshot, "profile")
    if not user and is_auth_error(snapshot.errors.get("profile")):
        raise AuthExpiredError(SESSION_EXPIRED_MESSAGE)
    if user:
        snapshot.user_id = str(_pick(user, "id", "uuid", "userId") or "")
        snapshot.user_name = str(
            _pick(user, "name", "userName", "user_name")
            or _display_name(user)
            or ""
        )

    user_id = snapshot.user_id or "me"
    memberships = _try_paths(
        session,
        [p.format(user_id=quote(user_id, safe="")) for p in MEMBERSHIP_PATHS[:3]],
        snapshot,
        "courses",
    )
    snapshot.courses = _parse_courses(memberships, session.base_url)
    session._tell("Loading courses…", 0.10)

    harvested: list[tuple[str, Any]] = []
    if not snapshot.courses:
        try:
            harvested = session.harvest_learn_json()
        except Exception as exc:
            snapshot.errors["harvest"] = str(exc)
        harvested_profile = _first_harvest(harvested, ("/users/me", "/utilities/self"))
        harvested_courses = _first_harvest(
            harvested, ("memberships", "/users/me/courses", "/ultra/course", "/courses?")
        )
        if not user and harvested_profile:
            user = harvested_profile
            snapshot.user_id = str(_pick(user, "id", "uuid", "userId") or "")
            snapshot.user_name = str(
                _pick(user, "name", "userName", "user_name")
                or _display_name(user)
                or ""
            )
            user_id = snapshot.user_id or "me"
        if harvested_courses:
            snapshot.courses = _parse_courses(harvested_courses, session.base_url)
            snapshot.errors.pop("courses", None)

    if course_ids:
        snapshot.courses = [course for course in snapshot.courses if course.id in course_ids]
        session._tell(f"Limiting to {len(snapshot.courses)} filtered courses…", 0.12)

    harvested_calendar = _first_harvest(harvested, ("calendar", "dueDate"))
    harvested_grades = _first_harvest(harvested, ("grade", "streams/ultra"))

    calendar_payloads: list[Any] = []
    if harvested_calendar:
        calendar_payloads.append(harvested_calendar)
    calendar_payloads.extend(_fetch_calendar_payloads(session, snapshot, user_id))
    calendar = _merge_calendar_payloads(*calendar_payloads)
    snapshot.deadlines, snapshot.assignments = _parse_calendar(
        calendar, snapshot.courses, session.base_url
    )
    if course_ids:
        snapshot.assignments = [
            item for item in snapshot.assignments if item.course_id in course_ids
        ]
        snapshot.deadlines = [
            item for item in snapshot.deadlines if item.course_id in course_ids
        ]
    session._tell("Loading deadlines…", 0.20)

    grades = harvested_grades or _try_paths(
        session,
        [p.format(user_id=quote(user_id, safe="")) for p in GRADE_STREAM_PATHS],
        snapshot,
        "grades",
    )
    snapshot.grades = _parse_grades(grades, snapshot.courses)
    mygrades = _fetch_mygrades(session, snapshot)
    if mygrades:
        snapshot.grades = _merge_mygrades(snapshot.grades, mygrades)
        snapshot.errors.pop("grades", None)
    elif snapshot.courses:
        extra = _fetch_course_grades(session, snapshot, user_id)
        if extra:
            snapshot.grades = _merge_mygrades(snapshot.grades, extra)
            snapshot.errors.pop("grades", None)
    if not snapshot.grades:
        try:
            harvested_more = session.harvest_learn_json(("/ultra/stream",))
            harvested_grades = _first_harvest(
                harvested_more, ("grade", "streams/ultra", "gradebook")
            )
            if harvested_grades:
                snapshot.grades = _parse_grades(harvested_grades, snapshot.courses)
        except Exception:
            pass
    if snapshot.grades:
        snapshot.errors.pop("grades", None)
    elif _is_soft_http_error(snapshot.errors.get("grades")):
        snapshot.errors.pop("grades", None)
    if course_ids:
        snapshot.grades = [item for item in snapshot.grades if item.course_id in course_ids]
    session._tell("Loading grades…", 0.28)

    if not quick:
        snapshot.announcements = _fetch_announcements(session, snapshot)

    _merge_assignments_from_deadlines(snapshot)
    _enrich_assignment_links(session, snapshot, quick=quick, include_files=include_files)
    _check_live_submissions(session, snapshot, quick=quick)
    snapshot.files_indexed = bool(include_files)
    _apply_assignment_status(snapshot)
    _merge_deadlines_from_assignments(snapshot)
    _enrich_last_activity(snapshot)
    session._tell("Finishing up…", 0.98)
    if not snapshot.courses:
        snapshot.errors.setdefault(
            "courses",
            "Signed in, but no course list was returned. Try Refresh, or confirm the school URL.",
        )
    return snapshot


def _first_harvest(harvested: list[tuple[str, Any]], needles: tuple[str, ...]) -> Any:
    for url, payload in harvested:
        lowered = url.lower()
        if any(needle.lower() in lowered for needle in needles):
            return payload
    return None


def _try_paths(
    session: BlackboardSession,
    paths: Iterable[str],
    snapshot: Snapshot,
    section: str,
) -> Any:
    last_error = ""
    for path in paths:
        try:
            return session.get_json(path)
        except ApiRequestError as exc:
            last_error = str(exc)
            if exc.status in (404, 405, 501):
                continue
        except Exception as exc:
            last_error = str(exc)
    if last_error:
        snapshot.errors[section] = last_error
    return None


def _calendar_query_window() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=186)
    end = now + timedelta(days=366)
    return (
        start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _fetch_calendar_payloads(
    session: BlackboardSession, snapshot: Snapshot, user_id: str
) -> list[Any]:
    since, until = _calendar_query_window()
    q_start = quote(since, safe="")
    q_end = quote(until, safe="")
    user = quote(user_id, safe="")
    paths = [
        f"/learn/api/v1/calendars/dueDateCalendarItems?startDate={q_start}&endDate={q_end}",
        f"/learn/api/v1/calendars/calendarItems?startDate={q_start}&endDate={q_end}",
        f"/learn/api/public/v1/calendars/items?since={q_start}&until={q_end}",
        f"/learn/api/v1/users/{user}/dueDateCalendarItems?startDate={q_start}&endDate={q_end}",
        f"/learn/api/v1/calendars/items?startDate={q_start}&endDate={q_end}",
    ]
    payloads: list[Any] = []
    got_full_calendar = False
    last_error = ""
    for path in paths:
        try:
            data = session.get_json(path)
        except ApiRequestError as exc:
            last_error = str(exc)
            continue
        except Exception as exc:
            last_error = str(exc)
            continue
        if not data:
            continue
        items = _as_list(data)
        if not items:
            continue
        payloads.append(data)
        lowered = path.lower()
        if "duedate" not in lowered:
            got_full_calendar = True
    if not got_full_calendar and hasattr(session, "harvest_learn_json"):
        try:
            harvested_more = session.harvest_learn_json(("/ultra/calendar",))
            extra = _first_harvest(
                harvested_more, ("calendarItems", "calendars/items", "calendar")
            )
            if extra:
                payloads.append(extra)
                got_full_calendar = True
        except Exception:
            pass
    if payloads:
        snapshot.errors.pop("calendar", None)
    elif last_error:
        snapshot.errors["calendar"] = last_error
    return payloads


def _merge_calendar_payloads(*payloads: Any) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for payload in payloads:
        for raw in _as_list(payload):
            if not isinstance(raw, dict):
                continue
            item_id = str(_pick(raw, "id", "itemId", "uuid") or "")
            title = str(_pick(raw, "title", "name", "subject") or "")
            when = parse_dt(
                _pick(raw, "startDate", "start", "dueDate", "endDate", "end", "date")
            )
            course = str(_pick(raw, "courseId", "calendarId") or "")
            key = item_id or f"{course}:{title.lower()}:{when}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(raw)
    return merged


def _is_soft_http_error(message: str | None) -> bool:
    if not message:
        return False
    return any(token in message for token in ("HTTP 404", "HTTP 405", "HTTP 501"))


def _fetch_course_grades(
    session: BlackboardSession,
    snapshot: Snapshot,
    user_id: str,
    *,
    courses: list[Course] | None = None,
) -> list[Grade]:
    grades: list[Grade] = []
    errors: list[str] = []
    chosen = courses if courses is not None else list(snapshot.courses)
    if hasattr(session, "get_json_many"):
        return _fetch_course_grades_parallel(session, snapshot, user_id, chosen)
    for course in chosen:
        for template in COURSE_GRADE_PATHS:
            path = template.format(
                course_id=quote(course.id, safe=""),
                user_id=quote(user_id, safe=""),
            )
            try:
                data = session.get_json(path)
            except ApiRequestError as exc:
                if exc.status not in (404, 405, 501):
                    errors.append(str(exc))
                continue
            except Exception as exc:
                errors.append(str(exc))
                continue
            parsed = _parse_grades(data, [course], default_course_id=course.id)
            if parsed:
                grades.extend(parsed)
                break
    if grades:
        snapshot.errors.pop("grades", None)
    elif errors:
        snapshot.errors["grades"] = errors[0]
    return grades


def _fetch_course_grades_parallel(
    session: BlackboardSession,
    snapshot: Snapshot,
    user_id: str,
    courses: list[Course],
) -> list[Grade]:
    """Try each gradebook URL for every remaining course at the same time."""
    grades: list[Grade] = []
    pending = list(courses)
    errors: list[str] = []
    for template in COURSE_GRADE_PATHS:
        if not pending:
            break
        paths = [
            template.format(
                course_id=quote(course.id, safe=""),
                user_id=quote(user_id, safe=""),
            )
            for course in pending
        ]
        try:
            rows = list(session.get_json_many(paths) or [])
        except Exception as exc:
            errors.append(str(exc))
            break
        if len(rows) < len(pending):
            rows.extend({} for _ in range(len(pending) - len(rows)))
        still: list[Course] = []
        for course, row in zip(pending, rows):
            status = int((row or {}).get("status") or 0)
            data = (row or {}).get("data")
            if status and status < 400 and data is not None:
                grades.extend(_parse_grades(data, [course], default_course_id=course.id))
                continue
            if status not in (404, 405, 501):
                errors.append(f"HTTP {status}")
            still.append(course)
        pending = still
    if grades:
        snapshot.errors.pop("grades", None)
    elif errors:
        snapshot.errors["grades"] = errors[0]
    return grades


def mygrades_path(course_id: str) -> str:
    return (
        "/webapps/bb-mygrades-BBLEARN/myGrades"
        f"?course_id={quote(course_id, safe='')}"
        "&stream_name=mygrades&is_stream=false"
    )


def _fetch_mygrades(session: BlackboardSession, snapshot: Snapshot) -> list[Grade]:
    """Read every course's My Grades page, several pages at a time."""
    courses = [course for course in snapshot.courses if _bb_pk(course.id)]
    if not courses or not hasattr(session, "get_html_documents"):
        return []
    grades: list[Grade] = []
    render_later: list[Course] = []
    total = len(courses)
    batch_size = 8
    for start in range(0, total, batch_size):
        batch = courses[start : start + batch_size]
        session._tell(
            f"Loading grades {start + 1}–{min(start + len(batch), total)} of {total}",
            0.20 + 0.06 * ((start + len(batch)) / total),
        )
        try:
            documents = session.get_html_documents([mygrades_path(course.id) for course in batch])
        except Exception:
            render_later.extend(batch)
            continue
        by_id = {
            _course_id_from_mygrades_url(str(document.get("url") or "")): document
            for document in documents or []
            if isinstance(document, dict)
        }
        for course in batch:
            document = by_id.get(course.id) or {}
            html = str(document.get("html") or "")
            status = int(document.get("status") or 0)
            parsed = _parse_mygrades_html(html, course.id) if html and status < 400 else []
            if parsed:
                grades.extend(parsed)
            elif _mygrades_html_needs_browser(html, status):
                render_later.append(course)
    if render_later and hasattr(session, "read_mygrades_pages"):
        grades.extend(_render_mygrades(session, render_later))
    return grades


def _render_mygrades(session: BlackboardSession, courses: list[Course]) -> list[Grade]:
    grades: list[Grade] = []
    batch_size = 4
    for start in range(0, len(courses), batch_size):
        batch = courses[start : start + batch_size]
        session._tell(
            f"Opening grade pages {start + 1}–{min(start + len(batch), len(courses))} of {len(courses)}",
            0.26,
        )
        try:
            pages = session.read_mygrades_pages([mygrades_path(course.id) for course in batch])
        except Exception:
            break
        if pages and all(bool(page.get("blocked")) for page in pages if isinstance(page, dict)):
            break
        by_id = {
            _course_id_from_mygrades_url(str(page.get("url") or "")): page
            for page in pages or []
            if isinstance(page, dict)
        }
        for course in batch:
            page = by_id.get(course.id) or {}
            grades.extend(_grades_from_dom_rows(page.get("rows"), course.id))
    return grades


def _course_id_from_mygrades_url(url: str) -> str:
    return (parse_qs(urlparse(url).query).get("course_id") or [""])[0]


def _mygrades_html_needs_browser(html: str, status: int) -> bool:
    """True when the download is a shell and the scores are drawn after the page loads."""
    if status in (404, 405, 501) or status >= 400:
        return False
    if not html:
        return True
    lowered = html.lower()
    if "itemrow" in lowered or "pointspossible" in lowered or "sortable_item_row" in lowered:
        return False
    if 'id="loginform"' in lowered or "id='loginform'" in lowered:
        return False
    return True


def _merge_mygrades(existing: list[Grade], fresh: list[Grade]) -> list[Grade]:
    covered = {grade.course_id for grade in fresh}
    kept = [grade for grade in existing if grade.course_id not in covered]
    return _dedupe_grades(kept + fresh)


_MYGRADES_ROW_RE = re.compile(
    r'''<(?:div|tr|li)\b[^>]*class=["'][^"']*(?:sortable_item_row|itemRow|graded_item_row|gradeRow)[^"']*["'][^>]*>''',
    re.IGNORECASE,
)
_CATEGORY_WORDS = {
    "assignment",
    "test",
    "quiz",
    "discussion",
    "journal",
    "survey",
    "作业",
    "测验",
    "讨论",
}
_SKIP_GRADE_TITLES = {
    "total",
    "weighted total",
    "running total",
    "overall grade",
    "总分",
    "加权总分",
    "总计",
    "总成绩",
}
_SUBMITTED_GRADE_WORDS = (
    "needs grading",
    "needsgrading",
    "submitted",
    "已提交",
    "需要评分",
    "待评分",
    "待批改",
)
_EMPTY_GRADE_WORDS = {"", "-", "—", "--", "n/a", "na", "none", "未提交", "未评分"}


def _grades_from_dom_rows(rows: Any, course_id: str) -> list[Grade]:
    grades: list[Grade] = []
    seen: set[str] = set()
    if not isinstance(rows, list):
        return []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _clean_html_text(str(row.get("title") or ""))
        if not title or title.lower() in _SKIP_GRADE_TITLES:
            continue
        label, earned, possible, feedback = _grade_with_feedback(
            str(row.get("grade") or ""),
            str(row.get("possible") or ""),
            str(row.get("feedback") or ""),
        )
        if label is None or title.lower() in seen:
            continue
        seen.add(title.lower())
        grades.append(
            Grade(
                id=f"{course_id}:{title}",
                course_id=course_id,
                title=title,
                score=label,
                posted_at=parse_dt(row.get("posted")),
                points_earned=earned,
                points_possible=possible,
                feedback=feedback,
            )
        )
    return grades


def _strip_hidden_grade_labels(html: str) -> str:
    return re.sub(
        r'<(?:span|div)\b[^>]*class=["\'][^"\']*\b(?:hideoff|offscreen|sr-only)\b[^"\']*["\'][^>]*>.*?</(?:span|div)>',
        " ",
        html or "",
        flags=re.IGNORECASE | re.DOTALL,
    )


def _parse_mygrades_html(html: str, course_id: str) -> list[Grade]:
    text = _strip_hidden_grade_labels(html or "")
    lowered = text.lower()
    login_wall = 'id="loginform"' in lowered or "id='loginform'" in lowered
    has_grade_markup = "itemrow" in lowered or "pointspossible" in lowered or "gradable" in lowered
    if login_wall and not has_grade_markup:
        return []
    matches = list(_MYGRADES_ROW_RE.finditer(text))
    chunks: list[str] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else match.end() + 4000
        chunks.append(text[match.start() : end])
    grades: list[Grade] = []
    seen: set[str] = set()
    for chunk in chunks:
        grade = _grade_from_mygrades_chunk(chunk, course_id)
        if grade is None or grade.title.lower() in seen:
            continue
        seen.add(grade.title.lower())
        grades.append(grade)
    return grades


def _grade_from_mygrades_chunk(chunk: str, course_id: str) -> Grade | None:
    if re.search(r"\bcalculatedRow\b", chunk, flags=re.IGNORECASE):
        return None
    title = _mygrades_title(chunk)
    if not title or title.lower() in _SKIP_GRADE_TITLES:
        return None
    cleaned, feedback = _pull_feedback_blocks(chunk)
    score_text = _best_grade_text(cleaned)
    possible_text = _class_inner_text(cleaned, "pointsPossible")
    label, earned, possible, feedback = _grade_with_feedback(score_text, possible_text, feedback)
    if label is None:
        return None
    posted = parse_dt(_class_inner_text(chunk, "lastActivityDate"))
    return Grade(
        id=f"{course_id}:{title}",
        course_id=course_id,
        title=title,
        score=label,
        posted_at=posted,
        points_earned=earned,
        points_possible=possible,
        feedback=feedback,
    )


def _mygrades_title(chunk: str) -> str:
    start = re.search(
        r'''class=["'][^"']*\bgradable\b[^"']*["'][^>]*>''',
        chunk,
        flags=re.IGNORECASE,
    )
    region = chunk[start.end() : start.end() + 2500] if start else chunk[:2500]
    stop = re.search(
        r'''<(?:div|span|td|tr)\b[^>]*class=["'][^"']*\b(?:grade|pointsPossible|activity|lastActivityDate)\b''',
        region,
        flags=re.IGNORECASE,
    )
    if stop and stop.start() > 0:
        region = region[: stop.start()]
    anchors = re.findall(r"<a\b[^>]*>(.*?)</a>", region, flags=re.IGNORECASE | re.DOTALL)
    texts = [_clean_html_text(anchor) for anchor in anchors]
    texts = [text for text in texts if text and text.lower() not in _CATEGORY_WORDS]
    if texts:
        return max(texts, key=len)
    plain = _clean_html_text(region)
    for word in _CATEGORY_WORDS:
        plain = re.sub(rf"\b{re.escape(word)}\b", " ", plain, flags=re.IGNORECASE)
    return " ".join(plain.split())


def _mygrades_score(
    score_text: str, possible_text: str
) -> tuple[str | None, float | None, float | None]:
    score = _clean_html_text(score_text)
    score = re.sub(r"^(?:grade|成绩)\s*[:：]?\s*", "", score, flags=re.IGNORECASE).strip()
    possible = _first_number(possible_text)
    compact = score.lower().replace(" ", "")
    if any(word in score.lower() for word in _SUBMITTED_GRADE_WORDS) or any(
        word in compact for word in ("needsgrading", "submitted")
    ):
        return "Submitted", None, possible
    fraction = _split_fraction(score.replace(" ", ""))
    if fraction:
        earned, possible_from_score = fraction
        if possible is None:
            possible = possible_from_score
        return f"{_trim_number(earned)}/{_trim_number(possible or possible_from_score)}", earned, possible
    earned = _as_number(score)
    if earned is not None and possible is not None:
        return f"{_trim_number(earned)}/{_trim_number(possible)}", earned, possible
    if earned is not None:
        return _trim_number(earned), earned, None
    if score and score.lower() not in _EMPTY_GRADE_WORDS and score not in _EMPTY_GRADE_WORDS:
        if possible is not None:
            return f"{score}/{_trim_number(possible)}", None, possible
        return score, None, None
    return None, None, None


def _grade_with_feedback(
    score_text: str, possible_text: str, feedback: str = ""
) -> tuple[str | None, float | None, float | None, str]:
    label, earned, possible = _mygrades_score(score_text, possible_text)
    note = (feedback or "").strip()
    if label and not _score_is_compact(label):
        label, earned, possible, extra = _split_mixed_score(label, earned, possible)
        note = note or extra
    if label is None and note:
        shown = f"—/{_trim_number(possible)}" if possible else "—"
        return shown, earned, possible, note
    return label, earned, possible, note


def _score_is_compact(score: str) -> bool:
    text = " ".join((score or "").split())
    if not text:
        return True
    if len(text) > 24 or len(text.split()) > 3:
        return False
    return True


def _split_mixed_score(
    score: str, earned: float | None, possible: float | None
) -> tuple[str, float | None, float | None, str]:
    """Separate a numeric score from teacher comments that were stored in the same text."""
    text = " ".join((score or "").split())
    trailing = re.match(r"^(.*?)\s*/\s*(\d+(?:\.\d+)?)\s*$", text)
    note = text
    if trailing:
        maybe = float(trailing.group(2))
        if possible is None or abs(maybe - possible) < 0.001:
            possible = maybe
            note = trailing.group(1).strip()
    leading = re.match(
        r"^(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*[-–—:]?\s*(.*)$",
        note,
    )
    if leading:
        earned = float(leading.group(1))
        possible = float(leading.group(2))
        note = leading.group(3).strip()
        return (
            f"{_trim_number(earned)}/{_trim_number(possible)}",
            earned,
            possible,
            note,
        )
    totaled = re.search(r"=\s*(\d+(?:\.\d+)?)\s*$", note)
    if totaled and possible:
        earned = float(totaled.group(1))
        note = note[: totaled.start()].strip(" -")
        return (
            f"{_trim_number(earned)}/{_trim_number(possible)}",
            earned,
            possible,
            note,
        )
    if _looks_like_filename(note):
        shown = f"—/{_trim_number(possible)}" if possible else "—"
        return shown, None, possible, ""
    if note:
        shown = f"—/{_trim_number(possible)}" if possible else "—"
        return shown, None, possible, note
    shown = f"—/{_trim_number(possible)}" if possible else "—"
    return shown, earned, possible, ""


def _looks_like_filename(text: str) -> bool:
    compact = " ".join((text or "").split())
    if not compact or len(compact.split()) > 3:
        return False
    return bool(
        re.search(r"\.(?:docx?|pdf|pptx?|xlsx?|txt|pages|zip)\b", compact, flags=re.IGNORECASE)
    )


_NOTE_CLASS_RE = re.compile(
    r"<(div|span|p|td)\b[^>]*class=[\"'][^\"']*\b(?:feedback|comments|comment|instructorcomment|gradecomment|itemcomments|usercomment)\b[^\"']*[\"'][^>]*>",
    re.IGNORECASE,
)


def _pull_feedback_blocks(html: str) -> tuple[str, str]:
    notes: list[str] = []
    pieces: list[str] = []
    pos = 0
    for match in _NOTE_CLASS_RE.finditer(html or ""):
        if match.start() < pos:
            continue
        pieces.append(html[pos : match.start()])
        tag = match.group(1)
        body_end = _find_closing_tag(html, match.end(), tag)
        notes.append(_clean_html_text(html[match.end() : body_end]))
        pos = body_end
        closer = re.match(rf"</{tag}\s*>", html[pos:], flags=re.IGNORECASE)
        if closer:
            pos += closer.end()
    pieces.append((html or "")[pos:])
    return "".join(pieces), "\n\n".join(note for note in notes if note)


def _find_closing_tag(html: str, start: int, tag: str) -> int:
    token = re.compile(rf"</?{tag}\b[^>]*>", flags=re.IGNORECASE)
    depth = 1
    for match in token.finditer(html, start):
        if match.group(0).startswith("</"):
            depth -= 1
            if depth == 0:
                return match.start()
        else:
            depth += 1
    return len(html)


def _best_grade_text(html: str) -> str:
    pattern = re.compile(
        r'''class=["'][^"']*\bgrade\b[^"']*["'][^>]*>(.*?)</(?:span|div|td|a)>''',
        flags=re.IGNORECASE | re.DOTALL,
    )
    compact: list[str] = []
    for match in pattern.finditer(html or ""):
        text = _clean_html_text(match.group(1))
        text = re.sub(r"^(?:grade|成绩)\s*[:：]?\s*", "", text, flags=re.IGNORECASE).strip()
        if text and _score_is_compact(text):
            compact.append(text)
    for text in compact:
        head = text.split("/")[0].strip()
        if _as_number(head) is not None or _split_fraction(text.replace(" ", "")):
            return text
    if compact:
        return compact[-1]
    return _class_inner_text(html, "grade")


def _class_inner_text(html: str, class_name: str) -> str:
    match = re.search(
        rf'''class=["'][^"']*\b{class_name}\b[^"']*["'][^>]*>(.*?)</(?:span|div|td|a)>''',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return _clean_html_text(match.group(1) if match else "")


def _clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
    )
    return " ".join(text.split())


def _first_number(value: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", value or "")
    if not match:
        return None
    return float(match.group(0))


def _fetch_announcements(
    session: BlackboardSession, snapshot: Snapshot
) -> list[Announcement]:
    items: list[Announcement] = []
    for course in snapshot.courses[:4]:
        for template in ANNOUNCEMENT_PATHS[:1]:
            path = template.format(course_id=quote(course.id, safe=""))
            try:
                data = session.get_json(path)
            except Exception:
                continue
            parsed = _parse_announcements(data, course.id)
            if parsed:
                items.extend(parsed)
                break
    return items


def _parse_courses(data: Any, base_url: str) -> list[Course]:
    courses: list[Course] = []
    seen: set[str] = set()
    for raw in _as_list(data):
        if not isinstance(raw, dict):
            continue
        course_blob = raw.get("course") if isinstance(raw.get("course"), dict) else raw
        course_id = str(
            _pick(course_blob, "id", "courseId", "uuid")
            or _pick(raw, "courseId", "id")
            or ""
        )
        name = str(
            _pick(course_blob, "name", "displayName", "courseName")
            or _pick(raw, "name")
            or "Untitled course"
        )
        if not course_id or course_id in seen:
            if course_id in seen:
                continue
            course_id = name
        term = _term_name(course_blob) or _term_name(raw)
        instructor = str(
            _pick(course_blob, "instructor", "instructorName")
            or _pick(raw, "instructor")
            or ""
        )
        url = str(_pick(course_blob, "url", "homePageUrl") or "")
        if not url:
            url = resolve_url(base_url, f"/ultra/courses/{course_id}/outline")
        last_activity = parse_dt(
            _pick(
                course_blob,
                "lastAccessed",
                "lastAccessDate",
                "modified",
                "modifiedDate",
                "updated",
            )
            or _pick(raw, "lastAccessed", "lastAccessDate", "modified")
        )
        seen.add(course_id)
        courses.append(
            Course(
                id=course_id,
                name=name,
                term=term,
                instructor=instructor,
                blackboard_url=url,
                last_activity=last_activity,
            )
        )
    return courses


def work_launch_url(
    base_url: str,
    *,
    item_id: str = "",
    course_id: str = "",
    content_id: str = "",
    explicit: str = "",
    handler: str = "",
    title: str = "",
) -> str:
    """Open the real Blackboard tool page for this item, not Ultra home."""
    explicit = (explicit or "").strip()
    raw_course = (course_id or "").strip()
    extracted_content, extracted_course = _ids_from_launch_url(explicit)
    forum_id, conf_id = _forum_ids_from_url(explicit)
    content_id = _bb_pk(content_id) or extracted_content
    course_pk = _bb_pk(raw_course) or extracted_course
    kind = _handler_kind(handler) or _guess_work_kind(title, handler)
    if _is_deep_work_url(explicit, base_url) and not _url_kind_mismatch(explicit, kind):
        return resolve_url(base_url, explicit)
    if kind == "discussion" and course_pk:
        return _discussion_launch_url(
            base_url,
            course_pk,
            content_id=content_id,
            forum_id=forum_id,
            conf_id=conf_id,
        )
    if content_id and course_pk:
        return _launch_url_for_handler(base_url, course_pk, content_id, handler)
    if raw_course or course_pk:
        return resolve_url(base_url, f"/ultra/courses/{raw_course or course_pk}/outline")
    return resolve_url(base_url, "/ultra")


def content_id_for_work(
    snapshot: Snapshot,
    *,
    assignment: Assignment | None = None,
    deadline: Deadline | None = None,
    item_id: str = "",
    explicit: str = "",
) -> str:
    if not assignment and deadline:
        assignment = snapshot.assignment_by_id(deadline.assignment_id or deadline.id)
    if assignment:
        stored = _trusted_content_id(assignment)
        matched = _content_id_from_grades(snapshot, assignment)
        if matched and (
            not stored
            or stored == matched
            or _bb_id_seq(matched) >= _bb_id_seq(stored)
        ):
            return matched
        if stored:
            return stored
    if deadline:
        stored = deadline.content_id if _bb_pk(deadline.content_id) and deadline.content_id != deadline.id else ""
        if stored:
            return stored
    extracted, _ = _ids_from_launch_url(explicit)
    if extracted and not _is_classic_assignment_url(explicit, ""):
        return extracted
    return ""


def _assignment_upload_url(base_url: str, course_id: str, content_id: str) -> str:
    query = urlencode(
        {
            "content_id": content_id,
            "course_id": course_id,
            "group_id": "",
            "mode": "view",
        }
    )
    return resolve_url(base_url, f"/webapps/assignment/uploadAssignment?{query}")


def _launch_url_for_handler(
    base_url: str, course_id: str, content_id: str, handler: str
) -> str:
    kind = _handler_kind(handler)
    if kind == "assessment":
        query = urlencode({"course_id": course_id, "content_id": content_id})
        return resolve_url(
            base_url, f"/webapps/assessment/take/launchAssessment.jsp?{query}"
        )
    if kind == "discussion":
        return _discussion_launch_url(base_url, course_id, content_id=content_id)
    return _assignment_upload_url(base_url, course_id, content_id)


def _discussion_launch_url(
    base_url: str,
    course_id: str,
    *,
    content_id: str = "",
    forum_id: str = "",
    conf_id: str = "",
) -> str:
    if forum_id:
        query = urlencode(
            {
                "action": "list_threads",
                "forum_id": forum_id,
                "nav": "discussion_board_entry",
                "conf_id": conf_id,
                "course_id": course_id,
                "content_id": content_id,
            }
        )
        return resolve_url(base_url, f"/webapps/discussionboard/do/forum?{query}")
    query = urlencode(
        {
            "toggle_mode": "read",
            "action": "list_forums",
            "course_id": course_id,
            "nav": "discussion_board_entry",
            "content_id": content_id,
        }
    )
    return resolve_url(base_url, f"/webapps/discussionboard/do/conference?{query}")


def _url_kind_mismatch(url: str, kind: str) -> bool:
    path = (urlparse(url).path or "").lower()
    if kind == "discussion" and "/webapps/assignment/" in path:
        return True
    if kind == "assessment" and "/webapps/assignment/" in path:
        return True
    if kind == "assignment" and "/webapps/discussionboard/" in path:
        return True
    return False


def _forum_ids_from_url(url: str) -> tuple[str, str]:
    if not url:
        return "", ""
    query = parse_qs(urlparse(url).query)
    forum_id = _bb_pk((query.get("forum_id") or query.get("forumId") or [""])[0])
    conf_id = _bb_pk(
        (query.get("conf_id") or query.get("conference_id") or query.get("confId") or [""])[0]
    )
    return forum_id, conf_id


def _handler_kind(handler: str) -> str:
    text = (handler or "").lower()
    if any(word in text for word in ("folder", "lesson")):
        return "folder"
    if "x-bb-file" in text or text.endswith("/file") or text.endswith(".file"):
        return "file"
    if "x-bb-document" in text or "document" in text:
        return "document"
    if any(word in text for word in ("externallink", "blti", "lti", "weblink")):
        return "link"
    if any(word in text for word in ("forum", "discussion", "x-bb-forum", "forumlink")):
        return "discussion"
    if any(
        word in text
        for word in ("asmt", "assessment", "test", "quiz", "survey", "exam")
    ):
        return "assessment"
    if "assign" in text:
        return "assignment"
    return ""


def _is_deep_work_url(url: str, base_url: str) -> bool:
    if not url or _is_shallow_blackboard_url(url, base_url):
        return False
    path = (urlparse(resolve_url(base_url, url)).path or "").lower()
    if "/ultra/" in path:
        return False
    return any(
        needle in path
        for needle in (
            "/webapps/assignment/",
            "/webapps/assessment/",
            "/webapps/discussionboard/",
            "/webapps/blackboard/execute/content/",
            "/webapps/blackboard/execute/launcher",
            "/webapps/blackboard/execute/blti",
            "/webapps/gradebook/",
            "/webapps/calendar/launch",
            "/webapps/collab-ultra/",
            "/webapps/lti/",
        )
    )


def _bb_pk(value: str) -> str:
    text = (value or "").strip()
    return text if _BB_PK.match(text) else ""


def _bb_id_seq(value: str) -> int:
    text = _bb_pk(value)
    if not text:
        return 0
    try:
        return int(text.strip("_").split("_", 1)[0])
    except ValueError:
        return 0


def _trusted_content_id(assignment: Assignment) -> str:
    content_id = _bb_pk(assignment.content_id)
    if content_id and content_id != assignment.id:
        return content_id
    return ""


def _titles_equal(left: str, right: str) -> bool:
    return bool(_norm_title(left)) and _norm_title(left) == _norm_title(right)


def _ids_from_launch_url(url: str) -> tuple[str, str]:
    if not url:
        return "", ""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    content = _bb_pk((query.get("content_id") or query.get("contentId") or [""])[0])
    course = _bb_pk((query.get("course_id") or query.get("courseId") or [""])[0])
    parts = [part for part in parsed.path.split("/") if part]
    if "courses" in parts:
        index = parts.index("courses")
        if index + 1 < len(parts):
            course = course or _bb_pk(parts[index + 1])
    if "assessment" in parts:
        index = parts.index("assessment")
        if index + 1 < len(parts):
            content = content or _bb_pk(parts[index + 1])
    return content, course


def _is_classic_assignment_url(url: str, base_url: str) -> bool:
    if not url:
        return False
    path = (urlparse(resolve_url(base_url, url)).path or "").lower()
    return "/webapps/assignment/uploadassignment" in path


def _is_shallow_blackboard_url(url: str, base_url: str) -> bool:
    resolved = resolve_url(base_url, url)
    path = (urlparse(resolved).path or "/").rstrip("/") or "/"
    lowered = path.lower()
    if path in {"/", "/ultra", "/ultra/stream", "/ultra/institution", "/webapps/portal"}:
        return True
    if path.endswith("/outline") and "/assessment/" not in lowered:
        return True
    if "/ultra/" in lowered and "/assessment/" in lowered:
        return True
    if "/webapps/calendar/launch/attempt/" in lowered:
        return True
    return False


def _calendar_course_id(raw: dict[str, Any], courses: list[Course]) -> str:
    names = {course.name.lower(): course.id for course in courses}
    ids = {course.id for course in courses}
    course_id = str(_pick(raw, "courseId", "rawCourseId", "contentHandlerCourseId") or "")
    calendar_id = str(_pick(raw, "calendarId") or "")
    calendar_name = str(_pick(raw, "calendarName", "courseName") or "")
    if course_id in ids:
        return course_id
    if calendar_id in ids:
        return calendar_id
    if calendar_name.lower() in names:
        return names[calendar_name.lower()]
    return course_id or calendar_id


def _calendar_content_id(raw: dict[str, Any]) -> str:
    blobs: list[dict[str, Any]] = [raw]
    for key in ("dynamicCalendarItemProps", "itemSpecificData", "item", "content"):
        value = raw.get(key)
        if isinstance(value, dict):
            blobs.append(value)
    for blob in blobs:
        candidate = _bb_pk(
            str(_pick(blob, "contentId", "content_id", "courseContentId") or "")
        )
        if candidate:
            return candidate
    return ""


def _calendar_handler(raw: dict[str, Any], title: str) -> str:
    text = " ".join(
        [
            str(_pick(raw, "itemType", "type", "eventType", "contentHandler") or ""),
            title,
        ]
    )
    kind = _handler_kind(text) or _guess_work_kind(title, str(_pick(raw, "contentHandler") or ""))
    if kind == "discussion":
        return "resource/x-bb-forumlink"
    if kind == "assessment":
        return "resource/x-bb-asmt-test-link"
    return ""


def _calendar_explicit_url(raw: dict[str, Any]) -> str:
    for key in ("url", "launchUrl", "itemUrl", "href", "link"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            inner = value.get("href") or value.get("url")
            if inner:
                return str(inner)
    return ""


def _parse_calendar(
    data: Any, courses: list[Course], base_url: str
) -> tuple[list[Deadline], list[Assignment]]:
    deadlines: list[Deadline] = []
    assignments: list[Assignment] = []

    for raw in _as_list(data):
        if not isinstance(raw, dict):
            continue
        item_id = str(_pick(raw, "id", "itemId", "uuid") or "")
        title = str(_pick(raw, "title", "name", "subject") or "Untitled")
        when = parse_dt(
            _pick(raw, "startDate", "start", "dueDate", "endDate", "end", "date")
        )
        course_id = _calendar_course_id(raw, courses)
        kind = _deadline_kind(raw)
        content_id = _calendar_content_id(raw)
        handler = _calendar_handler(raw, title)
        url = work_launch_url(
            base_url,
            item_id=item_id,
            course_id=course_id,
            content_id=content_id,
            explicit=_calendar_explicit_url(raw),
            handler=handler,
            title=title,
        )
        if not item_id:
            item_id = f"{course_id}:{title}:{when}"

        deadlines.append(
            Deadline(
                id=item_id,
                title=title,
                when=when,
                course_id=course_id,
                kind=kind,
                assignment_id=item_id if kind == "assignment" else "",
                blackboard_url=url,
                content_id=content_id,
                content_handler=handler,
            )
        )
        # Only coursework belongs on the Assignments page.
        if kind in ("assignment", "test"):
            assignments.append(
                Assignment(
                    id=item_id,
                    course_id=course_id,
                    title=title,
                    due_at=when,
                    status="submitted" if _looks_submitted(raw) else "todo",
                    blackboard_url=url,
                    description=str(_pick(raw, "description", "body") or ""),
                    content_id=content_id,
                    content_handler=handler,
                )
            )
    return deadlines, assignments


def _parse_grades(
    data: Any, courses: list[Course], default_course_id: str = ""
) -> list[Grade]:
    grades: list[Grade] = []
    names = {c.name.lower(): c.id for c in courses}
    for raw in _as_list(data):
        if not isinstance(raw, dict):
            continue
        item = raw.get("item") if isinstance(raw.get("item"), dict) else raw
        grade_id = str(_pick(item, "id", "columnId", "gradeId") or _pick(raw, "id") or "")
        title = str(
            _pick(item, "title", "name", "columnName", "displayName")
            or _pick(raw, "title", "name", "columnName", "displayName")
            or ""
        )
        if not title:
            for blob in (raw, item):
                if not isinstance(blob, dict):
                    continue
                for key in ("column", "columnDefinition", "gradeColumn"):
                    nested = blob.get(key)
                    if isinstance(nested, dict):
                        title = str(
                            _pick(nested, "displayName", "name", "title", "columnName") or ""
                        )
                    if title:
                        break
                if title:
                    break
        if not title:
            title = "Grade"
        course_id = str(
            _pick(raw, "courseId", "calendarId")
            or _pick(item, "courseId")
            or default_course_id
        )
        course_name = str(_pick(raw, "courseName", "calendarName") or "")
        if not course_id and course_name:
            course_id = names.get(course_name.lower(), "")
        score, points_earned, points_possible = _score_parts(raw, item)
        if _blank_score(score) and _grade_has_student_work(raw, item):
            score = "Submitted"
        posted = parse_dt(
            _pick(raw, "posted", "postedDate", "modified", "dateChanged", "created")
            or _pick(item, "posted", "modified")
        )
        assignment_id = str(
            _pick(raw, "contentId")
            or _pick(item, "contentId")
            or ""
        )
        if not grade_id:
            grade_id = f"{course_id}:{title}:{score}"
        grades.append(
            Grade(
                id=grade_id,
                course_id=course_id,
                title=title,
                score=score,
                posted_at=posted,
                assignment_id=assignment_id,
                points_earned=points_earned,
                points_possible=points_possible,
            )
        )
    return _dedupe_grades(grades)


def _parse_announcements(data: Any, course_id: str) -> list[Announcement]:
    items: list[Announcement] = []
    for raw in _as_list(data):
        if not isinstance(raw, dict):
            continue
        items.append(
            Announcement(
                id=str(_pick(raw, "id", "announcementId") or raw.get("title") or ""),
                course_id=course_id,
                title=str(_pick(raw, "title", "subject") or "Announcement"),
                body=str(_pick(raw, "body", "message", "text") or ""),
                posted_at=parse_dt(_pick(raw, "created", "modified", "postedDate")),
            )
        )
    return items


def _apply_assignment_status(snapshot: Snapshot) -> None:
    for assignment in snapshot.assignments:
        assignment.status = _resolve_assignment_status(snapshot, assignment)


def _resolve_assignment_status(snapshot: Snapshot, assignment: Assignment) -> AssignmentStatus:
    now = datetime.now(timezone.utc)
    if _has_submission(snapshot, assignment):
        return "submitted"
    due = _as_utc(assignment.due_at)
    if due and due < now:
        return "late"
    return "todo"


def _is_manually_submitted(snapshot: Snapshot, assignment: Assignment) -> bool:
    keys = snapshot.manual_submitted_keys
    if not keys:
        return False
    if assignment.id and assignment.id in keys:
        return True
    token = f"{assignment.course_id}::{(assignment.title or '').strip().lower()}"
    return token in keys


def _norm_title(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in (text or ""))
    return " ".join(cleaned.split())


def _titles_match(left: str, right: str) -> bool:
    a = _norm_title(left)
    b = _norm_title(right)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 6 and (a in b or b in a):
        return True
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return False
    overlap = ta & tb
    return bool(overlap) and (ta <= tb or tb <= ta) and len(overlap) >= 2


def _same_course(left: str, right: str) -> bool:
    if not left or not right:
        return True
    return left == right


def _blank_score(score: str) -> bool:
    return (score or "").strip().lower() in {"", "-", "—", "n/a", "na", "none"}


def _grade_has_student_work(raw: dict[str, Any], item: dict[str, Any]) -> bool:
    """True when the gradebook row itself shows student work, not just a column."""
    for blob in (raw, item):
        if not isinstance(blob, dict):
            continue
        status = (
            str(
                _pick(
                    blob,
                    "status",
                    "attemptStatus",
                    "gradingStatus",
                    "submissionStatus",
                    "gradeStatus",
                )
                or ""
            )
            .lower()
            .replace("_", "")
            .replace(" ", "")
        )
        if any(
            word in status
            for word in ("submit", "needsgrading", "graded", "posted", "attempted")
        ):
            return True
        if blob.get("hasStudentAttempt") or blob.get("submitted") or blob.get("isSubmitted"):
            return True
        for key in ("attemptCount", "attempts", "studentAttempts"):
            value = blob.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return True
            if isinstance(value, list) and value:
                return True
        nested = blob.get("submission") or blob.get("studentSubmission") or blob.get("attempt")
        if isinstance(nested, dict) and (
            nested.get("id")
            or nested.get("dateSubmitted")
            or nested.get("submittedDate")
            or nested.get("status")
        ):
            return True
    return False


def _grade_indicates_work(grade: Grade) -> bool:
    if grade.posted_at:
        return True
    return not _blank_score(grade.score)


def html_indicates_submission(html: str) -> bool:
    """True when a classic Learn assignment/test page already has student work."""
    text = html or ""
    title = ""
    match = re.search(
        r'id=["\']pageTitleText["\'][^>]*>(.*?)</span>',
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        title = re.sub(r"<[^>]+>", " ", match.group(1))
        title = " ".join(title.split())
    if not title:
        title_match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = " ".join(re.sub(r"<[^>]+>", " ", title_match.group(1)).split())
    title_l = title.lower()
    if any(
        marker in title
        for marker in (
            "复查提交历史记录",
            "复查测试提交",
            "复查测试结果",
            "查看提交收据",
        )
    ):
        return True
    if any(
        marker in title_l
        for marker in (
            "review submission history",
            "review test submission",
            "review test results",
            "submission receipt",
        )
    ):
        return True
    if re.search(r'id=["\']currentAttempt_attemptFile_', text):
        return True
    if re.search(r"/webapps/assignment/download\?[^\"']*attempt_id=_", text):
        return True
    if 'id="currentAttempt_submissionList"' in text and "attachment" in text.lower():
        return True
    return False


def _check_live_submissions(
    session: BlackboardSession, snapshot: Snapshot, *, quick: bool = False
) -> None:
    pending = [
        item
        for item in snapshot.assignments
        if item.blackboard_url
        and _is_deep_work_url(item.blackboard_url, session.base_url)
        and not item.has_attempt
    ]
    if not pending:
        return
    limit = 24 if quick else 60
    pending = pending[:limit]
    batch_size = 6
    by_url: dict[str, bool] = {}
    total = max(len(pending), 1)
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        session._tell(
            f"Checking submissions {start + 1}–{min(start + len(batch), len(pending))} of {len(pending)}",
            0.75 + 0.22 * (start / total),
        )
        try:
            rows = session.check_submission_pages([item.blackboard_url for item in batch])
        except Exception:
            continue
        for row in rows:
            if isinstance(row, dict):
                by_url[str(row.get("url") or "")] = bool(row.get("submitted"))
    for item in pending:
        resolved = resolve_url(session.base_url, item.blackboard_url)
        if by_url.get(item.blackboard_url) or by_url.get(resolved):
            item.has_attempt = True
            item.status = "submitted"


def _has_submission(snapshot: Snapshot, assignment: Assignment) -> bool:
    if _is_manually_submitted(snapshot, assignment):
        return True
    if assignment.has_attempt or assignment.status == "submitted":
        return True
    aid = str(assignment.id or "")
    matches: list[Grade] = []
    for grade in snapshot.grades:
        if not _grade_indicates_work(grade):
            continue
        if aid and aid in {str(grade.id), str(grade.assignment_id)}:
            return True
        if _titles_match(assignment.title, grade.title) and _same_course(
            assignment.course_id, grade.course_id
        ):
            return True
        if _norm_title(assignment.title) == _norm_title(grade.title):
            matches.append(grade)
    if len(matches) == 1:
        return True
    return False


def _looks_submitted(raw: dict[str, Any]) -> bool:
    status = str(
        _pick(
            raw,
            "status",
            "attemptStatus",
            "gradingStatus",
            "submissionStatus",
            "gradeStatus",
        )
        or ""
    ).lower()
    if any(
        word in status
        for word in (
            "submit",
            "complete",
            "graded",
            "needsgrading",
            "needs_grading",
            "needs grading",
            "posted",
            "attempted",
            "inprogress",
            "in_progress",
            "in progress",
        )
    ):
        return True
    for key in ("attemptCount", "attempts", "studentAttempts"):
        value = raw.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return True
        if isinstance(value, list) and value:
            return True
    if raw.get("hasStudentAttempt") or raw.get("submitted") or raw.get("isSubmitted"):
        return True
    nested = raw.get("submission") or raw.get("studentSubmission") or raw.get("attempt")
    if isinstance(nested, dict) and (
        nested.get("id")
        or nested.get("dateSubmitted")
        or nested.get("submittedDate")
        or nested.get("status")
    ):
        return True
    props = raw.get("dynamicCalendarItemProps")
    if isinstance(props, dict) and _looks_submitted(props):
        return True
    return False


def _merge_assignments_from_deadlines(snapshot: Snapshot) -> None:
    """Home/Calendar read deadlines; keep the Assignments page in sync with that list."""
    seen_ids = {item.id for item in snapshot.assignments}
    seen_keys = {(item.course_id, item.title.lower()) for item in snapshot.assignments}
    for deadline in snapshot.deadlines:
        if deadline.kind == "other":
            continue
        key = (deadline.course_id, deadline.title.lower())
        if deadline.id in seen_ids or key in seen_keys:
            continue
        snapshot.assignments.append(
            Assignment(
                id=deadline.id,
                course_id=deadline.course_id,
                title=deadline.title,
                due_at=deadline.when,
                status="todo",
                blackboard_url=deadline.blackboard_url,
                content_id=deadline.content_id,
                content_handler=deadline.content_handler,
            )
        )
        seen_ids.add(deadline.id)
        seen_keys.add(key)


def _merge_deadlines_from_assignments(snapshot: Snapshot) -> None:
    existing = {(d.course_id, d.title.lower()) for d in snapshot.deadlines}
    for assignment in snapshot.assignments:
        key = (assignment.course_id, assignment.title.lower())
        if key in existing:
            continue
        snapshot.deadlines.append(
            Deadline(
                id=assignment.id,
                title=assignment.title,
                when=assignment.due_at,
                course_id=assignment.course_id,
                kind="assignment",
                assignment_id=assignment.id,
                blackboard_url=assignment.blackboard_url,
                content_id=assignment.content_id,
                content_handler=assignment.content_handler,
            )
        )
    for deadline in snapshot.deadlines:
        if deadline.content_id:
            continue
        match = snapshot.assignment_by_id(deadline.assignment_id or deadline.id)
        if match and match.content_id:
            deadline.content_id = match.content_id
            deadline.blackboard_url = match.blackboard_url
            deadline.content_handler = match.content_handler


def _enrich_assignment_links(
    session: BlackboardSession,
    snapshot: Snapshot,
    *,
    quick: bool = False,
    include_files: bool = False,
) -> None:
    for assignment in snapshot.assignments:
        if assignment.content_id == assignment.id:
            assignment.content_id = ""
        if not assignment.content_id:
            assignment.content_id = _content_id_from_grades(snapshot, assignment)
    if include_files:
        catalog, nodes = crawl_course_catalog(session, snapshot, quick=quick, include_html=True)
        snapshot.content_nodes = nodes
        apply_content_catalog(snapshot, catalog)
        remaining = {
            item.course_id
            for item in snapshot.assignments
            if item.course_id and not _trusted_content_id(item)
        }
        if remaining:
            _fill_content_ids_from_columns(session, snapshot, remaining)
        snapshot.files_indexed = True
    _apply_launch_urls(snapshot, session.base_url)


@dataclass
class ContentEntry:
    course_id: str
    content_id: str
    title: str
    handler: str = ""
    url: str = ""
    due_at: datetime | None = None
    is_folder: bool = False
    forum_id: str = ""
    conf_id: str = ""


def crawl_course_catalog(
    session: BlackboardSession,
    snapshot: Snapshot,
    *,
    quick: bool = False,
    include_html: bool = True,
) -> tuple[list[ContentEntry], list[ContentNode]]:
    courses = [course for course in snapshot.courses if _bb_pk(course.id)]
    needed = {item.course_id for item in snapshot.assignments}
    courses.sort(key=lambda course: (0 if course.id in needed else 1, course.name.lower()))
    if quick:
        courses = [course for course in courses if course.id in needed][:12]
    else:
        courses = courses[:24]
    if hasattr(session, "get_json_many"):
        return _crawl_courses_parallel(
            session, courses, include_html=include_html
        )
    catalog: list[ContentEntry] = []
    nodes: list[ContentNode] = []
    total = max(len(courses), 1)
    for index, course in enumerate(courses):
        fraction = 0.32 + 0.43 * (index / total)
        session._tell(f"Indexing {index + 1} of {len(courses)}: {course.name}", fraction)
        try:
            course_entries, course_nodes = _catalog_for_course(
                session, course.id, session.base_url, include_html=include_html
            )
            catalog.extend(course_entries)
            nodes.extend(course_nodes)
        except Exception:
            continue
    if courses:
        session._tell("Finished indexing courses…", 0.75)
    return catalog, nodes


def _crawl_courses_parallel(
    session: BlackboardSession,
    courses: list[Course],
    *,
    include_html: bool,
) -> tuple[list[ContentEntry], list[ContentNode]]:
    """Load several courses at once, and each course's folders and files together."""
    catalog: list[ContentEntry] = []
    nodes: list[ContentNode] = []
    if not courses:
        return catalog, nodes
    total = len(courses)
    session._tell(f"Indexing {total} courses together…", 0.34)
    trees = _fetch_content_trees_parallel(session, [course.id for course in courses])
    session._tell(f"Loading folders in {total} courses…", 0.46)
    trees = _expand_children_parallel(session, trees)
    built: list[tuple[str, list[ContentEntry], list[ContentNode]]] = []
    for course in courses:
        items = trees.get(course.id) or []
        try:
            entries = [
                _entry_from_content_item(item, course.id, session.base_url) for item in items
            ]
            entries = [entry for entry in entries if entry.content_id or entry.title]
            course_nodes = content_nodes_from_items(items, course.id, session.base_url)
        except Exception:
            continue
        built.append((course.id, entries, course_nodes))
    session._tell(f"Loading files in {total} courses…", 0.58)
    _enrich_attachments_parallel(
        session,
        [(course_id, course_nodes) for course_id, _entries, course_nodes in built],
        session.base_url,
    )
    if include_html:
        _merge_parallel_html(session, built)
    else:
        for _course_id, entries, course_nodes in built:
            _apply_open_urls_from_catalog(course_nodes, entries)
    for _course_id, entries, course_nodes in built:
        catalog.extend(entries)
        nodes.extend(course_nodes)
    session._tell("Finished indexing courses…", 0.75)
    return catalog, nodes


def _fetch_content_trees_parallel(
    session: BlackboardSession, course_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    found: dict[str, list[dict[str, Any]]] = {}
    pending = list(course_ids)
    for template in COURSE_CONTENT_PATHS:
        if not pending:
            break
        paths = [
            template.format(course_id=quote(course_id, safe="")) for course_id in pending
        ]
        rows = _json_rows_for(session, paths)
        still: list[str] = []
        for course_id, row in zip(pending, rows):
            items = _walk_contents(row.get("data")) if _json_ok(row) else []
            if items:
                found[course_id] = items
            else:
                still.append(course_id)
        pending = still
    for course_id in pending:
        found.setdefault(course_id, [])
    return found


def _expand_children_parallel(
    session: BlackboardSession, trees: dict[str, list[dict[str, Any]]]
) -> dict[str, list[dict[str, Any]]]:
    states: dict[str, dict[str, Any]] = {}
    for course_id, items in trees.items():
        seen = {
            _bb_pk(str(_pick(item, "id", "contentId") or ""))
            for item in items
            if _bb_pk(str(_pick(item, "id", "contentId") or ""))
        }
        queue = [
            folder_id
            for item in items
            if _is_folder_item(item)
            for folder_id in [_bb_pk(str(_pick(item, "id", "contentId") or ""))]
            if folder_id
        ]
        states[course_id] = {"items": items, "seen": seen, "queue": queue, "done": set()}
    while True:
        pending: list[tuple[str, str]] = []
        for course_id, state in states.items():
            if len(state["items"]) >= 400:
                continue
            while state["queue"] and len(pending) < 48:
                folder_id = state["queue"].pop(0)
                if folder_id in state["done"]:
                    continue
                pending.append((course_id, folder_id))
        if not pending:
            break
        unresolved = list(pending)
        loaded: dict[tuple[str, str], Any] = {}
        for template in COURSE_CONTENT_CHILDREN:
            if not unresolved:
                break
            paths = [
                template.format(
                    course_id=quote(course_id, safe=""),
                    content_id=quote(folder_id, safe=""),
                )
                for course_id, folder_id in unresolved
            ]
            rows = _json_rows_for(session, paths)
            still: list[tuple[str, str]] = []
            for pair, row in zip(unresolved, rows):
                if _json_ok(row):
                    loaded[pair] = row.get("data")
                else:
                    still.append(pair)
            unresolved = still
        for course_id, folder_id in pending:
            state = states[course_id]
            state["done"].add(folder_id)
            data = loaded.get((course_id, folder_id))
            if not data or len(state["items"]) >= 400:
                continue
            for child in _walk_contents(data):
                child_id = _bb_pk(str(_pick(child, "id", "contentId") or ""))
                if child_id and child_id in state["seen"]:
                    continue
                if child_id:
                    state["seen"].add(child_id)
                if folder_id and not _pick(child, "parentId", "parent_id", "_parentId"):
                    child["_parentId"] = folder_id
                state["items"].append(child)
                if _is_folder_item(child) and child_id and child_id not in state["done"]:
                    state["queue"].append(child_id)
    return {course_id: state["items"] for course_id, state in states.items()}


def _enrich_attachments_parallel(
    session: BlackboardSession,
    groups: list[tuple[str, list[ContentNode]]],
    base_url: str,
) -> None:
    candidates: list[tuple[str, ContentNode]] = []
    for course_id, nodes in groups:
        chosen = [
            node
            for node in nodes
            if node.id
            and node.kind != "folder"
            and (
                node.kind == "file"
                or "file" in (node.handler or "").lower()
                or "document" in (node.handler or "").lower()
            )
        ][:80]
        candidates.extend((course_id, node) for node in chosen)
    fetched: dict[tuple[str, str], list[dict[str, Any]]] = {}
    pending = list(candidates)
    for template in COURSE_ATTACHMENT_PATHS:
        if not pending:
            break
        paths = [
            template.format(
                course_id=quote(course_id, safe=""),
                content_id=quote(node.id, safe=""),
            )
            for course_id, node in pending
        ]
        rows = _json_rows_for(session, paths)
        still: list[tuple[str, ContentNode]] = []
        for (course_id, node), row in zip(pending, rows):
            attachments = (
                [item for item in _as_list(row.get("data")) if isinstance(item, dict)]
                if _json_ok(row)
                else []
            )
            if attachments:
                fetched[(course_id, node.id)] = attachments
            else:
                still.append((course_id, node))
        pending = still
    by_course: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for (course_id, node_id), attachments in fetched.items():
        by_course.setdefault(course_id, {})[node_id] = attachments
    for course_id, nodes in groups:
        _apply_fetched_attachments(nodes, by_course.get(course_id) or {}, course_id, base_url)


def _merge_parallel_html(
    session: BlackboardSession,
    built: list[tuple[str, list[ContentEntry], list[ContentNode]]],
) -> None:
    pages: list[tuple[str, str]] = []
    for course_id, entries, _nodes in built:
        folder_ids = [
            entry.content_id for entry in entries if entry.is_folder and entry.content_id
        ][:20]
        urls = [
            f"/webapps/blackboard/execute/launcher?type=Course&id={course_id}",
            f"/webapps/blackboard/execute/modulepage/view?course_id={course_id}&mode=view",
            f"/webapps/discussionboard/do/conference?action=list_forums&course_id={course_id}&nav=discussion_board",
            f"/webapps/discussionboard/do/conference?action=list_forums&course_id={course_id}&nav=discussion_board_entry",
        ]
        for folder_id in folder_ids:
            urls.append(
                "/webapps/blackboard/content/listContent.jsp"
                f"?course_id={course_id}&content_id={folder_id}&mode=reset"
            )
        pages.extend((course_id, url) for url in urls)
    grouped: dict[str, list[tuple[str, str]]] = {course_id: [] for course_id, _e, _n in built}
    if pages and hasattr(session, "crawl_html_links"):
        total = len(pages)
        for start in range(0, total, 16):
            chunk = pages[start : start + 16]
            session._tell(
                f"Reading course pages {start + 1}–{min(start + len(chunk), total)} of {total}",
                0.62 + 0.1 * ((start + len(chunk)) / max(total, 1)),
            )
            try:
                raw_links = session.crawl_html_links([url for _course_id, url in chunk])
            except Exception:
                raw_links = []
            for row in raw_links or []:
                if not isinstance(row, dict):
                    continue
                course_id = _course_id_from_page_url(str(row.get("source") or ""))
                if course_id in grouped:
                    grouped[course_id].append(
                        (str(row.get("href") or ""), str(row.get("text") or ""))
                    )
    for course_id, entries, course_nodes in built:
        _merge_html_links(entries, course_id, grouped.get(course_id) or [], session.base_url)
        _apply_open_urls_from_catalog(course_nodes, entries)


def _json_rows_for(session: BlackboardSession, paths: list[str]) -> list[dict[str, Any]]:
    """One result per path, fetched together in small batches."""
    if not paths:
        return []
    indexed: dict[str, dict[str, Any]] = {}
    for start in range(0, len(paths), 24):
        chunk = paths[start : start + 24]
        try:
            rows = list(session.get_json_many(chunk) or [])
        except Exception:
            rows = []
        by_url = {
            str(row.get("url") or ""): row for row in rows if isinstance(row, dict)
        }
        for path in chunk:
            resolved = resolve_url(session.base_url, path).replace("/.learn/", "/learn/")
            indexed[path] = by_url.get(resolved) or by_url.get(path) or {}
    return [indexed.get(path) or {} for path in paths]


def _json_ok(row: dict[str, Any] | None) -> bool:
    if not isinstance(row, dict):
        return False
    status = int(row.get("status") or 0)
    return bool(status) and status < 400 and row.get("data") is not None


def _course_id_from_page_url(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    for key in ("course_id", "courseId", "id"):
        for value in query.get(key) or []:
            if _bb_pk(str(value)):
                return str(value)
    match = re.search(r"/courses/(_\d+_\d+)", url or "")
    return match.group(1) if match else ""


def apply_content_catalog(snapshot: Snapshot, catalog: list[ContentEntry]) -> None:
    if not catalog:
        return
    for assignment in snapshot.assignments:
        picked = _match_catalog_entry(assignment, catalog)
        if not picked:
            continue
        if picked.content_id:
            assignment.content_id = picked.content_id
        if picked.handler:
            assignment.content_handler = picked.handler
        if picked.url and (
            _is_deep_work_url(picked.url, "")
            or _handler_kind(picked.handler) in {"assignment", "assessment", "discussion"}
        ):
            assignment.blackboard_url = picked.url


def parse_html_links(html: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for href, text in _HTML_LINK_RE.findall(html or ""):
        clean = re.sub(r"<[^>]+>", " ", text)
        clean = " ".join(clean.split())
        if href:
            rows.append((href, clean))
    return rows


def _catalog_for_course(
    session: BlackboardSession,
    course_id: str,
    base_url: str,
    *,
    include_html: bool = True,
) -> tuple[list[ContentEntry], list[ContentNode]]:
    items = _fetch_course_content_tree(session, course_id)
    entries = [
        _entry_from_content_item(item, course_id, base_url) for item in items
    ]
    entries = [entry for entry in entries if entry.content_id or entry.title]
    nodes = content_nodes_from_items(items, course_id, base_url)
    _enrich_file_attachments(session, course_id, nodes, base_url)
    if not include_html:
        _apply_open_urls_from_catalog(nodes, entries)
        return entries, nodes
    folder_ids = [
        entry.content_id for entry in entries if entry.is_folder and entry.content_id
    ][:20]
    pages = [
        f"/webapps/blackboard/execute/launcher?type=Course&id={course_id}",
        f"/webapps/blackboard/execute/modulepage/view?course_id={course_id}&mode=view",
        f"/webapps/discussionboard/do/conference?action=list_forums&course_id={course_id}&nav=discussion_board",
        f"/webapps/discussionboard/do/conference?action=list_forums&course_id={course_id}&nav=discussion_board_entry",
    ]
    for folder_id in folder_ids:
        pages.append(
            "/webapps/blackboard/content/listContent.jsp"
            f"?course_id={course_id}&content_id={folder_id}&mode=reset"
        )
    try:
        raw_links = session.crawl_html_links(pages)
    except Exception:
        raw_links = []
    html_links = [
        (str(row.get("href") or ""), str(row.get("text") or ""))
        for row in raw_links
        if isinstance(row, dict)
    ]
    _merge_html_links(entries, course_id, html_links, base_url)
    _apply_open_urls_from_catalog(nodes, entries)
    return entries, nodes


def _fetch_course_content_tree(
    session: BlackboardSession, course_id: str
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for template in COURSE_CONTENT_PATHS:
        path = template.format(course_id=quote(course_id, safe=""))
        try:
            data = session.get_json(path)
        except Exception:
            continue
        items = _walk_contents(data)
        if items:
            break
    if items and any(_is_folder_item(item) for item in items):
        items = _expand_content_children(session, course_id, items)
    return items


def _expand_content_children(
    session: BlackboardSession, course_id: str, items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    seen = {
        _bb_pk(str(_pick(item, "id", "contentId") or ""))
        for item in items
        if _bb_pk(str(_pick(item, "id", "contentId") or ""))
    }
    queue = [item for item in items if _is_folder_item(item)]
    while queue and len(items) < 400:
        folder = queue.pop(0)
        folder_id = _bb_pk(str(_pick(folder, "id", "contentId") or ""))
        if not folder_id:
            continue
        children = None
        for template in COURSE_CONTENT_CHILDREN:
            path = template.format(
                course_id=quote(course_id, safe=""),
                content_id=quote(folder_id, safe=""),
            )
            try:
                children = session.get_json(path)
                break
            except Exception:
                continue
        if not children:
            continue
        for child in _walk_contents(children):
            child_id = _bb_pk(str(_pick(child, "id", "contentId") or ""))
            if child_id and child_id in seen:
                continue
            if child_id:
                seen.add(child_id)
            if folder_id and not _pick(child, "parentId", "parent_id", "_parentId"):
                child["_parentId"] = folder_id
            items.append(child)
            if _is_folder_item(child):
                queue.append(child)
    return items


def _entry_from_content_item(
    item: dict[str, Any], course_id: str, base_url: str
) -> ContentEntry:
    content_id = _bb_pk(str(_pick(item, "id", "contentId") or ""))
    handler = _content_handler_id(item)
    title = str(_pick(item, "title", "name") or "")
    due = parse_dt(
        _pick(item, "dueDate", "endDate") or _availability_due(item)
    )
    url = _content_api_url(item, base_url, course_id)
    forum_id, conf_id = _forum_ids_from_item(item)
    if url:
        url_forum, url_conf = _forum_ids_from_url(url)
        forum_id = forum_id or url_forum
        conf_id = conf_id or url_conf
    kind = _handler_kind(handler)
    if not url and content_id and kind in {"assignment", "assessment", "discussion"}:
        url = (
            _discussion_launch_url(
                base_url,
                course_id,
                content_id=content_id,
                forum_id=forum_id,
                conf_id=conf_id,
            )
            if kind == "discussion"
            else _launch_url_for_handler(base_url, course_id, content_id, handler)
        )
    return ContentEntry(
        course_id=course_id,
        content_id=content_id,
        title=title,
        handler=handler,
        url=url,
        due_at=due,
        is_folder=kind == "folder" or _is_folder_item(item),
        forum_id=forum_id,
        conf_id=conf_id,
    )


def _forum_ids_from_item(item: dict[str, Any]) -> tuple[str, str]:
    handler = item.get("contentHandler")
    blobs: list[dict[str, Any]] = [item]
    if isinstance(handler, dict):
        blobs.append(handler)
        for key in ("discussionTarget", "target", "forum", "gradebook"):
            nested = handler.get(key)
            if isinstance(nested, dict):
                blobs.append(nested)
    forum_id = ""
    conf_id = ""
    for blob in blobs:
        forum_id = forum_id or _bb_pk(
            str(_pick(blob, "forumId", "forum_id", "targetId", "discussionId") or "")
        )
        conf_id = conf_id or _bb_pk(
            str(_pick(blob, "conferenceId", "conf_id", "confId") or "")
        )
    return forum_id, conf_id


def _content_handler_id(item: dict[str, Any]) -> str:
    handler = item.get("contentHandler")
    if isinstance(handler, dict):
        return str(_pick(handler, "id", "name") or "")
    return str(handler or "")


def _is_folder_item(item: dict[str, Any]) -> bool:
    handler = _content_handler_id(item).lower()
    if any(word in handler for word in ("folder", "lesson")):
        return True
    return bool(item.get("hasChildren"))


def content_nodes_from_items(
    items: list[dict[str, Any]], course_id: str, base_url: str
) -> list[ContentNode]:
    nodes: list[ContentNode] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        node = _node_from_content_item(item, course_id, base_url)
        if node.id or node.title:
            nodes.append(node)
    return nodes


def _node_from_content_item(
    item: dict[str, Any], course_id: str, base_url: str
) -> ContentNode:
    content_id = _bb_pk(str(_pick(item, "id", "contentId") or ""))
    handler = _content_handler_id(item)
    kind = _handler_kind(handler) or ("folder" if _is_folder_item(item) else "link")
    if kind in {"assignment", "assessment", "discussion"}:
        kind = "link"
    title = str(_pick(item, "title", "name") or "")
    handler_blob = item.get("contentHandler") if isinstance(item.get("contentHandler"), dict) else {}
    filename = str(
        _pick(handler_blob, "fileName", "name")
        or _pick(item, "fileName", "filename")
        or ""
    )
    mime = str(_pick(handler_blob, "mimeType", "contentType") or _pick(item, "mimeType") or "")
    size = _as_int(_pick(item, "size", "fileSize") or _pick(handler_blob, "fileSize", "size"))
    modified = parse_dt(
        _pick(item, "modified", "updated", "modifiedDate", "lastModified")
        or _pick(handler_blob, "modified")
    )
    created = parse_dt(_pick(item, "created", "createdDate", "createdOn"))
    parent_id = _bb_pk(
        str(_pick(item, "parentId", "parent_id", "_parentId") or "")
    )
    open_url = _content_api_url(item, base_url, course_id)
    if not open_url and content_id:
        if kind == "folder":
            open_url = resolve_url(
                base_url,
                "/webapps/blackboard/content/listContent.jsp"
                f"?course_id={course_id}&content_id={content_id}&mode=reset",
            )
        else:
            open_url = resolve_url(
                base_url,
                f"/webapps/blackboard/execute/content/file?cmd=view&content_id={content_id}&course_id={course_id}",
            )
    extension = _extension_of(filename or title, mime)
    if _is_folder_item(item) or kind == "folder":
        kind = "folder"
    elif kind == "file" or filename or extension:
        kind = "file"
    else:
        kind = "link"
    return ContentNode(
        id=content_id or f"{course_id}:{title}",
        course_id=course_id,
        parent_id=parent_id,
        title=title,
        filename=filename,
        kind=kind if kind in {"folder", "file", "link"} else "link",
        handler=handler,
        mime=mime,
        extension=extension,
        size_bytes=size,
        modified_at=modified,
        created_at=created,
        open_url=open_url,
        download_path="",
    )


def _as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _extension_of(name: str, mime: str = "") -> str:
    text = (name or "").strip()
    if "." in text:
        ext = text.rsplit(".", 1)[-1].lower()
        if 1 <= len(ext) <= 8 and ext.isalnum():
            return ext
    mime = (mime or "").lower()
    mapping = {
        "pdf": "pdf",
        "msword": "doc",
        "wordprocessingml": "docx",
        "spreadsheetml": "xlsx",
        "presentationml": "pptx",
        "ms-excel": "xls",
        "ms-powerpoint": "ppt",
        "zip": "zip",
        "png": "png",
        "jpeg": "jpg",
        "jpg": "jpg",
        "gif": "gif",
        "mp4": "mp4",
        "plain": "txt",
    }
    for needle, ext in mapping.items():
        if needle in mime:
            return ext
    return ""


def _enrich_file_attachments(
    session: BlackboardSession, course_id: str, nodes: list[ContentNode], base_url: str
) -> None:
    candidates = [
        node
        for node in nodes
        if node.id
        and node.kind != "folder"
        and (
            node.kind == "file"
            or "file" in (node.handler or "").lower()
            or "document" in (node.handler or "").lower()
        )
    ][:80]
    fetched: dict[str, list[dict[str, Any]]] = {}
    for node in candidates:
        attachments = _fetch_attachments(session, course_id, node.id)
        if attachments:
            fetched[node.id] = attachments
    _apply_fetched_attachments(nodes, fetched, course_id, base_url)


def _apply_fetched_attachments(
    nodes: list[ContentNode],
    fetched: dict[str, list[dict[str, Any]]],
    course_id: str,
    base_url: str,
) -> None:
    extra: list[ContentNode] = []
    for node in list(nodes):
        attachments = fetched.get(node.id) or []
        if not attachments:
            continue
        if len(attachments) == 1:
            _apply_attachment(node, attachments[0], course_id, base_url)
        else:
            node.kind = "folder"
            for attachment in attachments:
                extra.append(_attachment_child(node, attachment, course_id, base_url))
    nodes.extend(extra)


def _fetch_attachments(
    session: BlackboardSession, course_id: str, content_id: str
) -> list[dict[str, Any]]:
    for template in COURSE_ATTACHMENT_PATHS:
        path = template.format(
            course_id=quote(course_id, safe=""),
            content_id=quote(content_id, safe=""),
        )
        try:
            data = session.get_json(path)
        except Exception:
            continue
        rows = [row for row in _as_list(data) if isinstance(row, dict)]
        if rows:
            return rows
    return []


def _apply_attachment(
    node: ContentNode, attachment: dict[str, Any], course_id: str, base_url: str
) -> None:
    filename = str(_pick(attachment, "fileName", "name", "title") or node.filename or node.title)
    mime = str(_pick(attachment, "mimeType", "contentType") or node.mime)
    size = _as_int(_pick(attachment, "size", "fileSize") or node.size_bytes)
    att_id = str(_pick(attachment, "id", "attachmentId") or "")
    node.kind = "file"
    node.filename = filename
    node.mime = mime or node.mime
    node.size_bytes = size or node.size_bytes
    node.extension = _extension_of(filename, mime) or node.extension
    if att_id:
        node.download_path = (
            f"/learn/api/public/v1/courses/{quote(course_id, safe='')}"
            f"/contents/{quote(node.id, safe='')}/attachments/{quote(att_id, safe='')}/download"
        )
        if not node.open_url:
            node.open_url = resolve_url(base_url, node.download_path)


def _attachment_child(
    parent: ContentNode, attachment: dict[str, Any], course_id: str, base_url: str
) -> ContentNode:
    filename = str(_pick(attachment, "fileName", "name", "title") or "File")
    mime = str(_pick(attachment, "mimeType", "contentType") or "")
    size = _as_int(_pick(attachment, "size", "fileSize"))
    att_id = str(_pick(attachment, "id", "attachmentId") or filename)
    download_path = (
        f"/learn/api/public/v1/courses/{quote(course_id, safe='')}"
        f"/contents/{quote(parent.id, safe='')}/attachments/{quote(att_id, safe='')}/download"
    )
    return ContentNode(
        id=f"{parent.id}:{att_id}",
        course_id=course_id,
        parent_id=parent.id,
        title=filename,
        filename=filename,
        kind="file",
        handler=parent.handler,
        mime=mime,
        extension=_extension_of(filename, mime),
        size_bytes=size,
        modified_at=parent.modified_at,
        created_at=parent.created_at,
        open_url=resolve_url(base_url, download_path),
        download_path=download_path,
    )


def _apply_open_urls_from_catalog(
    nodes: list[ContentNode], entries: list[ContentEntry]
) -> None:
    by_id = {entry.content_id: entry for entry in entries if entry.content_id}
    for node in nodes:
        entry = by_id.get(node.id)
        if entry and entry.url and not node.open_url:
            node.open_url = entry.url


def content_children(
    nodes: list[ContentNode], course_id: str, parent_id: str
) -> list[ContentNode]:
    rows = [
        node
        for node in nodes
        if node.course_id == course_id and (node.parent_id or "") == (parent_id or "")
    ]
    rows.sort(key=lambda node: (0 if node.kind == "folder" else 1, node.display_name().lower()))
    return rows


def _availability_due(item: dict[str, Any]) -> Any:
    availability = item.get("availability")
    if isinstance(availability, dict):
        adaptive = availability.get("adaptiveRelease")
        if isinstance(adaptive, dict):
            end = adaptive.get("endDate") or adaptive.get("dueDate")
            if end:
                return end
        return availability.get("endDate") or availability.get("dueDate")
    return None


def _content_api_url(item: dict[str, Any], base_url: str, course_id: str) -> str:
    candidates: list[Any] = [
        item.get("url"),
        item.get("launchUrl"),
        item.get("alternateLink"),
        item.get("href"),
    ]
    links = item.get("links") or item.get("_links")
    if isinstance(links, dict):
        candidates.extend(links.values())
    elif isinstance(links, list):
        candidates.extend(links)
    for value in candidates:
        href = ""
        if isinstance(value, str):
            href = value.strip()
        elif isinstance(value, dict):
            href = str(value.get("href") or value.get("url") or "").strip()
        if not href:
            continue
        url = resolve_url(base_url, href)
        if _is_deep_work_url(url, base_url):
            return url
    return ""


def _merge_html_links(
    entries: list[ContentEntry],
    course_id: str,
    links: list[tuple[str, str]],
    base_url: str,
) -> None:
    by_id = {
        entry.content_id: entry
        for entry in entries
        if entry.course_id == course_id and entry.content_id
    }
    for href, text in links:
        if not href or href.startswith("#"):
            continue
        url = resolve_url(base_url, href)
        path = (urlparse(url).path or "").lower()
        is_forum = "/webapps/discussionboard/" in path
        if not _is_deep_work_url(url, base_url) and not is_forum:
            continue
        content_id, _course = _ids_from_launch_url(url)
        forum_id, conf_id = _forum_ids_from_url(url)
        if content_id and content_id in by_id:
            by_id[content_id].url = url
            if forum_id:
                by_id[content_id].forum_id = forum_id
            if conf_id:
                by_id[content_id].conf_id = conf_id
            if is_forum:
                by_id[content_id].handler = (
                    by_id[content_id].handler or "resource/x-bb-forumlink"
                )
            continue
        matches = [
            entry
            for entry in entries
            if entry.course_id == course_id
            and not entry.is_folder
            and (
                _titles_equal(entry.title, text)
                or (is_forum and text and _titles_match(entry.title, text))
            )
        ]
        if len(matches) == 1:
            matches[0].url = url
            if content_id:
                matches[0].content_id = content_id
            if forum_id:
                matches[0].forum_id = forum_id
            if conf_id:
                matches[0].conf_id = conf_id
            if is_forum:
                matches[0].handler = matches[0].handler or "resource/x-bb-forumlink"


def _match_catalog_entry(
    assignment: Assignment, catalog: list[ContentEntry]
) -> ContentEntry | None:
    rows = [
        entry
        for entry in catalog
        if _same_course(assignment.course_id, entry.course_id) and not entry.is_folder
    ]
    if assignment.content_id:
        by_id = [entry for entry in rows if entry.content_id == assignment.content_id]
        if by_id:
            rows = by_id
    exact = [entry for entry in rows if _titles_equal(assignment.title, entry.title)]
    if not exact:
        return rows[0] if assignment.content_id and len(rows) == 1 else None
    kind = _guess_work_kind(assignment.title, assignment.content_handler)
    due_hits = [entry for entry in exact if _due_close(assignment.due_at, entry.due_at)]
    pool = due_hits or exact
    pool.sort(
        key=lambda entry: (
            -_handler_rank(kind, entry.handler),
            -_bb_id_seq(entry.content_id),
        )
    )
    return pool[0]


def _guess_work_kind(title: str, handler: str = "") -> str:
    known = _handler_kind(handler)
    if known:
        return known
    text = (title or "").lower()
    if not text:
        return ""
    if any(word in text for word in ("discussion", "forum")):
        return "discussion"
    if any(word in text for word in ("quiz", "test", "exam", "assessment")):
        return "test"
    return "assignment"


def _handler_rank(kind: str, handler: str) -> int:
    current = _handler_kind(handler)
    if kind == "discussion" and current == "discussion":
        return 4
    if kind == "test" and current == "assessment":
        return 4
    if kind == "assignment" and current == "assignment":
        return 4
    if current in {"assignment", "assessment", "discussion"}:
        return 2
    return 0


def _due_close(left: datetime | None, right: datetime | None) -> bool:
    start = _as_utc(left)
    end = _as_utc(right)
    if not start or not end:
        return False
    return abs((start - end).total_seconds()) <= 3 * 86400


def _content_id_from_grades(snapshot: Snapshot, assignment: Assignment) -> str:
    links: list[tuple[str, str, str, datetime | None]] = []
    for grade in snapshot.grades:
        candidate = _bb_pk(grade.assignment_id)
        if not candidate or not _same_course(assignment.course_id, grade.course_id):
            continue
        if _titles_equal(assignment.title, grade.title) or (
            assignment.id and assignment.id == str(grade.id)
        ):
            links.append((grade.title, str(grade.id), candidate, None))
    return _pick_content_id(assignment, links)


def _pick_content_id(
    assignment: Assignment, links: list[tuple[str, str, str, datetime | None]]
) -> str:
    exact = [row for row in links if _titles_equal(assignment.title, row[0])]
    if exact:
        by_due = _content_id_matching_due(assignment.due_at, exact)
        if by_due:
            return by_due
        return _newest_content_id(exact)
    by_column = [
        row
        for row in links
        if assignment.id and assignment.id == row[1] and _bb_pk(row[2])
    ]
    if len(by_column) == 1:
        return by_column[0][2]
    return ""


def _content_id_matching_due(
    due: datetime | None, links: list[tuple[str, str, str, datetime | None]]
) -> str:
    due_at = _as_utc(due)
    if not due_at:
        return ""
    scored: list[tuple[float, int, str]] = []
    for _title, _column_id, content_id, when in links:
        column_due = _as_utc(when)
        if not column_due:
            continue
        delta = abs((column_due - due_at).total_seconds())
        if delta <= 3 * 86400:
            scored.append((delta, -_bb_id_seq(content_id), content_id))
    if not scored:
        return ""
    scored.sort()
    return scored[0][2]


def _newest_content_id(links: list[tuple[str, str, str, datetime | None]]) -> str:
    if not links:
        return ""
    return max(links, key=lambda row: _bb_id_seq(row[2]))[2]


def _fill_content_ids_from_columns(
    session: BlackboardSession, snapshot: Snapshot, course_ids: set[str]
) -> None:
    courses = [course for course in snapshot.courses if course.id in course_ids]
    for course in courses[:16]:
        data = None
        for template in COURSE_COLUMN_PATHS:
            path = template.format(course_id=quote(course.id, safe=""))
            try:
                data = session.get_json(path)
                break
            except Exception:
                continue
        if not data:
            continue
        apply_column_content_ids(snapshot, course.id, _column_content_ids(data))


def apply_column_content_ids(
    snapshot: Snapshot,
    course_id: str,
    columns: list[tuple[str, str, str, datetime | None]],
) -> None:
    if not columns:
        return
    for assignment in snapshot.assignments:
        if assignment.course_id != course_id:
            continue
        picked = _pick_content_id(assignment, columns)
        if picked:
            assignment.content_id = picked


def _column_content_ids(data: Any) -> list[tuple[str, str, str, datetime | None]]:
    rows: list[tuple[str, str, str, datetime | None]] = []
    for raw in _as_list(data):
        if not isinstance(raw, dict):
            continue
        item = raw.get("column") if isinstance(raw.get("column"), dict) else raw
        title = str(_pick(item, "name", "title", "columnName") or _pick(raw, "name", "title") or "")
        column_id = str(_pick(item, "id", "columnId") or _pick(raw, "id") or "")
        content_id = _bb_pk(
            str(_pick(item, "contentId", "content_id") or _pick(raw, "contentId") or "")
        )
        grading = item.get("grading") if isinstance(item.get("grading"), dict) else raw.get("grading")
        due = parse_dt(
            _pick(item, "due", "dueDate", "endDate")
            or _pick(raw, "due", "dueDate")
            or (_pick(grading, "due", "dueDate") if isinstance(grading, dict) else None)
        )
        if title and content_id:
            rows.append((title, column_id, content_id, due))
    return rows


def _fill_content_ids_from_contents(
    session: BlackboardSession, snapshot: Snapshot, course_ids: set[str]
) -> None:
    courses = [course for course in snapshot.courses if course.id in course_ids]
    for course in courses[:12]:
        data = None
        for template in COURSE_CONTENT_PATHS:
            path = template.format(course_id=quote(course.id, safe=""))
            try:
                data = session.get_json(path)
                break
            except Exception:
                continue
        if not data:
            continue
        contents = [
            item
            for item in _walk_contents(data)
            if _bb_pk(str(_pick(item, "id", "contentId") or ""))
        ]
        if not contents:
            continue
        for assignment in snapshot.assignments:
            if assignment.course_id != course.id or _trusted_content_id(assignment):
                continue
            exact = [
                item
                for item in contents
                if _titles_equal(assignment.title, str(_pick(item, "title", "name") or ""))
            ]
            typed = [item for item in exact if _looks_assignment_content(item)]
            pool = typed or exact
            if not pool:
                continue
            pool.sort(
                key=lambda item: _bb_id_seq(
                    _bb_pk(str(_pick(item, "id", "contentId") or ""))
                ),
                reverse=True,
            )
            assignment.content_id = _bb_pk(str(_pick(pool[0], "id", "contentId") or ""))


def _looks_assignment_content(item: dict[str, Any]) -> bool:
    handler = item.get("contentHandler")
    if isinstance(handler, dict):
        handler = _pick(handler, "id", "name")
    text = str(handler or "").lower()
    return any(
        word in text for word in ("assignment", "assessment", "test", "quiz", "forum", "discussion")
    )


def _walk_contents(data: Any, parent_id: str = "") -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in _as_list(data):
        if not isinstance(raw, dict):
            continue
        if parent_id and not _pick(raw, "parentId", "parent_id", "_parentId"):
            raw["_parentId"] = parent_id
        items.append(raw)
        own_id = _bb_pk(str(_pick(raw, "id", "contentId") or ""))
        for key in ("children", "contents"):
            nested = raw.get(key)
            if nested is not None:
                items.extend(_walk_contents(nested, own_id or parent_id))
    return items


def _apply_launch_urls(snapshot: Snapshot, base_url: str) -> None:
    for assignment in snapshot.assignments:
        assignment.blackboard_url = work_launch_url(
            base_url,
            item_id=assignment.id,
            course_id=assignment.course_id,
            content_id=assignment.content_id,
            explicit=assignment.blackboard_url,
            handler=assignment.content_handler,
            title=assignment.title,
        )
    for deadline in snapshot.deadlines:
        match = snapshot.assignment_by_id(deadline.assignment_id or deadline.id)
        if match:
            if not deadline.content_id:
                deadline.content_id = match.content_id
            if not deadline.content_handler:
                deadline.content_handler = match.content_handler
            if match.blackboard_url:
                deadline.blackboard_url = match.blackboard_url
        deadline.blackboard_url = work_launch_url(
            base_url,
            item_id=deadline.id,
            course_id=deadline.course_id,
            content_id=deadline.content_id,
            explicit=deadline.blackboard_url,
            handler=deadline.content_handler,
            title=deadline.title,
        )


def _enrich_last_activity(snapshot: Snapshot) -> None:
    for course in snapshot.courses:
        times: list[datetime] = []
        if course.last_activity:
            times.append(_as_utc(course.last_activity))
        for assignment in snapshot.assignments:
            if assignment.course_id == course.id and assignment.due_at:
                times.append(_as_utc(assignment.due_at))
        for grade in snapshot.grades:
            if grade.course_id == course.id and grade.posted_at:
                times.append(_as_utc(grade.posted_at))
        for deadline in snapshot.deadlines:
            if deadline.course_id == course.id and deadline.when:
                times.append(_as_utc(deadline.when))
        for note in snapshot.announcements:
            if note.course_id == course.id and note.posted_at:
                times.append(_as_utc(note.posted_at))
        if times:
            course.last_activity = max(times)


def _deadline_kind(raw: dict[str, Any]) -> DeadlineKind:
    item_type = str(_pick(raw, "itemType", "type", "eventType") or "")
    handler = str(_pick(raw, "contentHandler") or "")
    title = str(_pick(raw, "title", "name", "subject") or "")
    type_key = item_type.lower().replace("_", "").replace(" ", "")
    text = f"{item_type} {handler} {title}".lower()
    if type_key in {
        "officehours",
        "officehour",
        "institution",
        "institutional",
        "personal",
        "course",
        "courseevent",
        "event",
        "calendarevent",
        "schedule",
        "courseschedule",
        "classmeeting",
        "announcement",
        "ultraannouncement",
    } or "event" in type_key or "schedule" in type_key:
        return "other"
    if any(word in text for word in ("office hour", "meeting", "holiday", "vacation")):
        return "other"
    if any(word in text for word in ("test", "quiz", "exam", "assessment")):
        return "test"
    if any(word in text for word in ("assign", "homework", "work", "due", "gradebook")):
        return "assignment"
    # Ultra due-date items are often unlabeled GradebookColumn / CalendarItem entries.
    return "assignment"


def _format_score(raw: dict[str, Any], item: dict[str, Any]) -> str:
    return _score_parts(raw, item)[0]


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return float(text)
    return None


def _trim_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def _split_fraction(text: str) -> tuple[float, float] | None:
    match = re.fullmatch(
        r"\s*(-?\d+(?:\.\d+)?)\s*/\s*(-?\d+(?:\.\d+)?)\s*", text or ""
    )
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def _find_number(blob: Any, keys: tuple[str, ...], depth: int = 0) -> float | None:
    if depth > 5:
        return None
    if isinstance(blob, dict):
        for key in keys:
            number = _as_number(blob.get(key))
            if number is not None:
                return number
        for value in blob.values():
            if isinstance(value, (dict, list)):
                found = _find_number(value, keys, depth + 1)
                if found is not None:
                    return found
    elif isinstance(blob, list):
        for value in blob:
            found = _find_number(value, keys, depth + 1)
            if found is not None:
                return found
    return None


_POSSIBLE_KEYS = ("possible", "pointsPossible", "possiblePoints", "maxScore", "maxPoints")


def _score_parts(
    raw: dict[str, Any], item: dict[str, Any]
) -> tuple[str, float | None, float | None]:
    display = _pick(raw, "displayGrade", "grade", "score", "text") or _pick(
        item, "displayGrade", "grade", "score"
    )
    text = ""
    earned: float | None = None
    possible = _find_number(raw, _POSSIBLE_KEYS)
    if possible is None:
        possible = _find_number(item, _POSSIBLE_KEYS)
    if isinstance(display, dict):
        text = str(_pick(display, "text", "display") or "")
        earned = _as_number(_pick(display, "score"))
        if earned is None:
            earned = _as_number(text)
        nested_possible = _as_number(_pick(display, "possible", "pointsPossible"))
        if nested_possible is not None:
            possible = nested_possible
    elif display not in (None, ""):
        text = str(display)
        earned = _as_number(display)
    fraction = _split_fraction(text)
    if fraction:
        earned, possible = fraction
        text = f"{_trim_number(earned)}/{_trim_number(possible)}"
    elif earned is not None and possible is not None:
        text = f"{_trim_number(earned)}/{_trim_number(possible)}"
    elif text and possible is not None and "/" not in text:
        text = f"{text}/{_trim_number(possible)}"
    return text, earned, possible


def _term_name(blob: Any) -> str:
    if not isinstance(blob, dict):
        return ""
    term = blob.get("term")
    if isinstance(term, dict):
        return str(_pick(term, "name", "id") or "")
    return str(_pick(blob, "term", "termName") or "")


def _display_name(user: dict[str, Any]) -> str:
    given = _pick(user, "givenName", "firstName")
    family = _pick(user, "familyName", "lastName")
    if given or family:
        return f"{given} {family}".strip()
    return ""


def _as_list(data: Any) -> list[Any]:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in (
            "results",
            "items",
            "value",
            "contents",
            "calendarItems",
            "grades",
            "memberships",
            "announcements",
        ):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def _pick(data: Any, *keys: str) -> Any:
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 1e12 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        return _as_utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def assignment_for_work(
    snapshot: Snapshot,
    *,
    assignment_id: str = "",
    title: str = "",
    course_id: str = "",
) -> Assignment | None:
    aid = str(assignment_id or "")
    if aid:
        found = snapshot.assignment_by_id(aid)
        if found:
            return found
        for assignment in snapshot.assignments:
            if assignment.content_id and assignment.content_id == aid:
                return assignment
    if not title:
        return None
    matches = [
        assignment
        for assignment in snapshot.assignments
        if _titles_match(assignment.title, title)
        and _same_course(assignment.course_id, course_id)
    ]
    if matches:
        return matches[0]
    return None


def deadline_is_finished(snapshot: Snapshot, deadline: Deadline) -> bool:
    """True when the calendar item is submitted or already graded."""
    assignment = assignment_for_work(
        snapshot,
        assignment_id=deadline.assignment_id or deadline.id,
        title=deadline.title,
        course_id=deadline.course_id,
    )
    if assignment is None:
        assignment = Assignment(
            id=deadline.assignment_id or deadline.id,
            course_id=deadline.course_id,
            title=deadline.title,
            due_at=deadline.when,
            blackboard_url=deadline.blackboard_url,
            content_id=deadline.content_id,
            content_handler=deadline.content_handler,
        )
    return _resolve_assignment_status(snapshot, assignment) == "submitted"


def upcoming(
    snapshot: Snapshot, days: int, *, now: datetime | None = None
) -> list[Deadline]:
    moment = _as_utc(now) if now else datetime.now(timezone.utc)
    limit = moment.timestamp() + days * 86400
    items = []
    for deadline in snapshot.deadlines:
        when = _as_utc(deadline.when)
        if when is None:
            continue
        if moment.timestamp() - 12 * 3600 <= when.timestamp() <= limit:
            items.append(deadline)
    items.sort(key=lambda d: _as_utc(d.when) or datetime.max.replace(tzinfo=timezone.utc))
    return items


def calendar_items_in_range(
    snapshot: Snapshot, start: datetime, end: datetime
) -> list[Deadline]:
    start_ts = _as_utc(start).timestamp()
    end_ts = _as_utc(end).timestamp()
    items = []
    for deadline in snapshot.deadlines:
        when = _as_utc(deadline.when)
        if when is None:
            continue
        if start_ts <= when.timestamp() < end_ts:
            items.append(deadline)
    items.sort(key=lambda d: _as_utc(d.when) or datetime.max.replace(tzinfo=timezone.utc))
    return items


def calendar_week_start(day: date) -> date:
    """Monday-first week, matching Google Calendar in China."""
    return day - timedelta(days=day.weekday())


def add_months(day: date, delta: int) -> date:
    month_index = day.month - 1 + delta
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    if month <= 0:
        month += 12
        year -= 1
    last_day = (
        date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
        - timedelta(days=1)
    ).day
    return date(year, month, min(day.day, last_day))


def event_is_all_day(when: datetime | None) -> bool:
    if when is None:
        return True
    local = _as_utc(when).astimezone()
    return local.hour == 0 and local.minute == 0 and local.second == 0


def local_event_date(when: datetime | None) -> date | None:
    if when is None:
        return None
    return _as_utc(when).astimezone().date()


def recent_grades(snapshot: Snapshot, limit: int = 8) -> list[Grade]:
    grades = list(snapshot.grades)
    grades.sort(
        key=lambda g: _as_utc(g.posted_at) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return grades[:limit]


_PENDING_SCORE_LABELS = {
    "submitted",
    "needs grading",
    "needsgrading",
    "needs_grading",
    "in progress",
    "inprogress",
    "pending",
    "not graded",
    "ungraded",
    "awaiting grade",
}


def is_posted_grade(score: str) -> bool:
    text = (score or "").strip()
    if _blank_score(text):
        return False
    key = text.lower().replace("_", " ")
    compact = key.replace(" ", "")
    return key not in _PENDING_SCORE_LABELS and compact not in _PENDING_SCORE_LABELS


def grade_parts(grade: Grade) -> tuple[str, float | None, float | None, str]:
    """Score label, earned, possible, and teacher feedback kept out of the score."""
    feedback = (grade.feedback or "").strip()
    score = (grade.score or "").strip()
    earned = grade.points_earned
    possible = grade.points_possible
    if feedback and _score_is_compact(score):
        return _compact_score_label(score, earned, possible), earned, possible, feedback
    if _score_is_compact(score):
        return _compact_score_label(score, earned, possible), earned, possible, ""
    label, earned, possible, note = _split_mixed_score(score, earned, possible)
    return label, earned, possible, feedback or note


def grade_note(grade: Grade) -> str:
    return grade_parts(grade)[3]


def _compact_score_label(
    score: str, earned: float | None, possible: float | None
) -> str:
    text = " ".join(score.split())
    fraction = _split_fraction(text)
    if fraction:
        return f"{_trim_number(fraction[0])}/{_trim_number(fraction[1])}"
    if earned is not None and possible:
        return f"{_trim_number(earned)}/{_trim_number(possible)}"
    if text and possible and "/" not in text and text.lower() != "submitted" and _as_number(text) is not None:
        return f"{_trim_number(float(text))}/{_trim_number(possible)}"
    if text:
        return text
    if possible:
        return f"—/{_trim_number(possible)}"
    return "Submitted"


def grade_points(grade: Grade) -> tuple[float, float] | None:
    label, earned, possible, _note = grade_parts(grade)
    if earned is None or possible is None:
        fraction = _split_fraction(label)
        if fraction:
            earned, possible = fraction
    if earned is None or possible is None or possible <= 0:
        return None
    if not is_posted_grade(label):
        return None
    return earned, possible


def format_grade_label(grade: Grade | None) -> str:
    if grade is None:
        return "Submitted"
    label, earned, possible, _note = grade_parts(grade)
    if earned is not None and possible:
        if is_posted_grade(label):
            return f"{_trim_number(earned)}/{_trim_number(possible)}"
    if label and not _blank_score(label):
        return label
    return "Submitted"


def course_score_totals(snapshot: Snapshot, course_id: str) -> tuple[float, float] | None:
    earned = 0.0
    possible = 0.0
    found = False
    for grade in snapshot.grades:
        if grade.course_id != course_id:
            continue
        points = grade_points(grade)
        if not points:
            continue
        earned += points[0]
        possible += points[1]
        found = True
    if not found or possible <= 0:
        return None
    return earned, possible


def course_score_percent(snapshot: Snapshot, course_id: str) -> float | None:
    totals = course_score_totals(snapshot, course_id)
    if not totals:
        return None
    return totals[0] / totals[1] * 100


def grade_due_at(snapshot: Snapshot, grade: Grade) -> datetime | None:
    assignment = assignment_for_work(
        snapshot,
        assignment_id=grade.assignment_id or grade.id,
        title=grade.title,
        course_id=grade.course_id,
    )
    if assignment and assignment.due_at:
        return assignment.due_at
    for deadline in snapshot.deadlines:
        if deadline.course_id != grade.course_id:
            continue
        if _titles_match(deadline.title, grade.title):
            return deadline.when
    return grade.posted_at


def course_result_rows(
    snapshot: Snapshot, course_id: str
) -> list[tuple[str, str, datetime | None, str]]:
    """Past work for one course: title, score label, due date, assignment id."""
    rows: list[tuple[str, str, datetime | None, str]] = []
    grades = [grade for grade in snapshot.grades if grade.course_id == course_id]
    used: set[int] = set()

    def matching_grade(title: str, assignment_id: str) -> tuple[int, Grade] | None:
        for index, grade in enumerate(grades):
            if index in used:
                continue
            if assignment_id and assignment_id in {grade.id, grade.assignment_id}:
                return index, grade
        for index, grade in enumerate(grades):
            if index in used:
                continue
            if _titles_match(grade.title, title):
                return index, grade
        return None

    for assignment in snapshot.assignments:
        if assignment.course_id != course_id:
            continue
        status = _resolve_assignment_status(snapshot, assignment)
        found = matching_grade(assignment.title, assignment.id)
        grade = found[1] if found else None
        posted = grade is not None and is_posted_grade(grade.score)
        if status != "submitted" and not posted:
            continue
        if found:
            used.add(found[0])
        label = format_grade_label(grade) if posted else "Submitted"
        rows.append((assignment.title, label, assignment.due_at, assignment.id))

    for index, grade in enumerate(grades):
        if index in used:
            continue
        if not is_posted_grade(grade.score) and not _grade_indicates_work(grade):
            continue
        label = format_grade_label(grade) if is_posted_grade(grade.score) else "Submitted"
        rows.append((grade.title, label, grade_due_at(snapshot, grade), grade.assignment_id or ""))

    def sort_key(row: tuple[str, str, datetime | None, str]) -> float:
        due = _as_utc(row[2])
        return due.timestamp() if due else float("-inf")

    rows.sort(key=sort_key, reverse=True)
    return rows


def index_course_files(session: BlackboardSession, snapshot: Snapshot) -> None:
    """Load course file trees without the slower HTML page walk."""
    catalog, nodes = crawl_course_catalog(session, snapshot, include_html=False)
    snapshot.content_nodes = nodes
    apply_content_catalog(snapshot, catalog)
    _apply_launch_urls(snapshot, session.base_url)
    snapshot.files_indexed = True


def _grade_rank(grade: Grade) -> tuple:
    posted = 1 if is_posted_grade(grade.score) else 0
    when = _as_utc(grade.posted_at)
    stamp = when.timestamp() if when else 0.0
    return (posted, stamp, len(grade.score or ""))


def _dedupe_grades(grades: list[Grade]) -> list[Grade]:
    by_id: dict[str, Grade] = {}
    id_order: list[str] = []
    for grade in grades:
        gid = grade.id or f"{grade.course_id}:{_norm_title(grade.title)}:{grade.score}"
        existing = by_id.get(gid)
        if existing is None:
            by_id[gid] = grade
            id_order.append(gid)
        elif _grade_rank(grade) > _grade_rank(existing):
            by_id[gid] = grade

    by_title: dict[tuple[str, str], Grade] = {}
    title_order: list[tuple[str, str]] = []
    for gid in id_order:
        grade = by_id[gid]
        key = (grade.course_id, _norm_title(grade.title))
        existing = by_title.get(key)
        if existing is None:
            by_title[key] = grade
            title_order.append(key)
        elif _grade_rank(grade) > _grade_rank(existing):
            by_title[key] = grade
    return [by_title[key] for key in title_order]


def grade_page_groups(snapshot: Snapshot) -> tuple[list[Grade], list[Grade]]:
    """Split work into posted grades vs submitted-but-ungraded. Hide the rest."""
    graded: list[Grade] = []
    pending: list[Grade] = []
    claimed_ids: set[str] = set()
    claimed_titles: set[tuple[str, str]] = set()

    def claim(grade: Grade) -> None:
        if grade.assignment_id:
            claimed_ids.add(grade.assignment_id)
        if grade.id:
            claimed_ids.add(grade.id)
        claimed_titles.add((grade.course_id, _norm_title(grade.title)))

    def assignment_claimed(assignment: Assignment) -> bool:
        if assignment.id and assignment.id in claimed_ids:
            return True
        return (assignment.course_id, _norm_title(assignment.title)) in claimed_titles

    for grade in _dedupe_grades(snapshot.grades):
        if is_posted_grade(grade.score):
            graded.append(grade)
            claim(grade)
        elif _grade_row_is_submitted(snapshot, grade):
            pending.append(grade)
            claim(grade)

    for assignment in snapshot.assignments:
        if assignment.status != "submitted" and not assignment.has_attempt:
            continue
        if assignment_claimed(assignment):
            continue
        row = Grade(
            id=assignment.id,
            course_id=assignment.course_id,
            title=assignment.title,
            score="Submitted",
            posted_at=None,
            assignment_id=assignment.id,
        )
        pending.append(row)
        claim(row)

    oldest = datetime.min.replace(tzinfo=timezone.utc)
    graded.sort(key=lambda g: _as_utc(g.posted_at) or oldest, reverse=True)
    pending.sort(key=lambda g: (snapshot.course_name(g.course_id).lower(), g.title.lower()))
    return graded, pending


def _grade_row_is_submitted(snapshot: Snapshot, grade: Grade) -> bool:
    text = (grade.score or "").strip().lower().replace("_", " ")
    compact = text.replace(" ", "")
    if text in _PENDING_SCORE_LABELS or compact in _PENDING_SCORE_LABELS:
        return True
    aid = str(grade.assignment_id or "")
    if aid:
        assignment = snapshot.assignment_by_id(aid)
        if assignment and (assignment.has_attempt or assignment.status == "submitted"):
            return True
    for assignment in snapshot.assignments:
        if not (assignment.has_attempt or assignment.status == "submitted"):
            continue
        if _titles_match(assignment.title, grade.title) and _same_course(
            assignment.course_id, grade.course_id
        ):
            return True
    return False


def assignments_for(
    snapshot: Snapshot,
    status: AssignmentStatus | Literal["all"] = "all",
    *,
    query: str = "",
    hide_overdue: str = "off",
) -> list[Assignment]:
    items = list(snapshot.assignments)
    seen_ids = {item.id for item in items}
    seen_keys = {(item.course_id, item.title.lower()) for item in items}
    now = datetime.now(timezone.utc)
    for deadline in snapshot.deadlines:
        if deadline.kind == "other":
            continue
        key = (deadline.course_id, deadline.title.lower())
        if deadline.id in seen_ids or key in seen_keys:
            continue
        stub = Assignment(
            id=deadline.id,
            course_id=deadline.course_id,
            title=deadline.title,
            due_at=deadline.when,
            status="todo",
            blackboard_url=deadline.blackboard_url,
            content_id=deadline.content_id,
            content_handler=deadline.content_handler,
        )
        stub.status = _resolve_assignment_status(snapshot, stub)
        items.append(stub)
        seen_ids.add(deadline.id)
        seen_keys.add(key)
    for assignment in items:
        assignment.status = _resolve_assignment_status(snapshot, assignment)
    if status != "all":
        items = [a for a in items if a.status == status]
    needle = query.strip().lower()
    if needle:
        filtered: list[Assignment] = []
        for assignment in items:
            course = snapshot.course_name(assignment.course_id).lower()
            haystack = f"{assignment.title} {course}".lower()
            if needle in haystack:
                filtered.append(assignment)
        items = filtered
    hide_days = {"1w": 7, "1m": 30}.get(hide_overdue)
    if hide_days:
        cutoff = now - timedelta(days=hide_days)
        items = [
            assignment
            for assignment in items
            if not (
                assignment.status == "late"
                and _as_utc(assignment.due_at) is not None
                and _as_utc(assignment.due_at) < cutoff
            )
        ]
    items.sort(key=lambda a: _as_utc(a.due_at) or datetime.max.replace(tzinfo=timezone.utc))
    return items
