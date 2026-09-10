"""Smoke tests for models, parsers, and view builders."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from blackboard.api import _parse_calendar, _parse_courses, _parse_grades, upcoming, work_launch_url
from blackboard.auth import (
    ApiRequestError,
    AuthExpiredError,
    candidate_base_urls,
    is_auth_error,
    url_looks_logged_in,
)
from blackboard.models import (
    Announcement,
    Assignment,
    ContentNode,
    Course,
    Deadline,
    Grade,
    Snapshot,
)
from blackboard.store import Store


def load_sample(store: Store | None = None) -> Snapshot:
    store = store or Store()
    now = datetime.now(timezone.utc)
    store.snapshot = Snapshot(
        user_name="Sample Student",
        user_id="sample",
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
    store.signed_in = True
    return store.snapshot


class ParserTests(unittest.TestCase):
    def test_login_url_detection(self) -> None:
        self.assertTrue(url_looks_logged_in("https://shs.blackboard.cn/ultra/course"))
        self.assertTrue(
            url_looks_logged_in(
                "https://shs.blackboardchina.cn/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1"
            )
        )
        self.assertFalse(url_looks_logged_in("https://shs.blackboard.cn/webapps/login"))
        self.assertFalse(url_looks_logged_in("https://id.school.edu/cas/login"))

    def test_candidate_base_urls_prefer_configured_then_known_hosts(self) -> None:
        urls = candidate_base_urls("https://shs.blackboard.cn")
        self.assertEqual(urls[0], "https://shs.blackboardchina.cn")
        self.assertIn("https://shs.blackboard.cn", urls)

    def test_parse_courses_memberships(self) -> None:
        data = {
            "results": [
                {
                    "courseId": "_1_1",
                    "course": {
                        "id": "_1_1",
                        "name": "English",
                        "term": {"name": "Fall 2026"},
                        "instructor": "Ms. Chen",
                    },
                }
            ]
        }
        courses = _parse_courses(data, "https://shs.blackboard.cn")
        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0].name, "English")
        self.assertEqual(courses[0].term, "Fall 2026")
        self.assertIn("/ultra/courses/_1_1/", courses[0].blackboard_url)

    def test_parse_calendar_assignments(self) -> None:
        data = {
            "results": [
                {
                    "id": "c1",
                    "title": "Essay 3",
                    "start": "2026-09-10T15:59:00.000Z",
                    "calendarId": "eng",
                    "itemType": "Assignment",
                }
            ]
        }
        deadlines, assignments = _parse_calendar(data, [], "https://shs.blackboard.cn")
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0].title, "Essay 3")
        self.assertEqual(deadlines[0].kind, "assignment")
        self.assertTrue(assignments[0].blackboard_url)

    def test_parse_calendar_builds_upload_assignment_url(self) -> None:
        data = {
            "results": [
                {
                    "id": "_99_1",
                    "title": "20260902 HW",
                    "start": "2026-09-02T14:00:00.000Z",
                    "calendarId": "_7949_1",
                    "contentId": "_241672_1",
                    "itemType": "Assignment",
                }
            ]
        }
        _, assignments = _parse_calendar(
            data, [], "https://shs.blackboardchina.cn"
        )
        self.assertEqual(assignments[0].content_id, "_241672_1")
        self.assertIn("uploadAssignment", assignments[0].blackboard_url)
        self.assertIn("content_id=_241672_1", assignments[0].blackboard_url)
        self.assertIn("course_id=_7949_1", assignments[0].blackboard_url)

    def test_unlabeled_calendar_items_become_assignments(self) -> None:
        data = {
            "results": [
                {
                    "id": "c2",
                    "title": "Problem set 4",
                    "start": "2026-09-12T15:59:00.000Z",
                    "calendarId": "math",
                    "itemType": "GradebookColumn",
                }
            ]
        }
        deadlines, assignments = _parse_calendar(data, [], "https://shs.blackboard.cn")
        self.assertEqual(len(deadlines), 1)
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0].title, "Problem set 4")

    def test_work_launch_url_skips_home_and_outline(self) -> None:
        base = "https://shs.blackboardchina.cn"
        expected = (
            f"{base}/webapps/assignment/uploadAssignment"
            "?content_id=_241672_1&course_id=_7949_1&group_id=&mode=view"
        )
        from_home = work_launch_url(
            base,
            explicit=f"{base}/ultra",
            content_id="_241672_1",
            course_id="_7949_1",
        )
        self.assertEqual(from_home, expected)
        from_outline = work_launch_url(
            base,
            explicit=f"{base}/ultra/courses/_7949_1/outline",
            content_id="_241672_1",
            course_id="_7949_1",
        )
        self.assertEqual(from_outline, expected)
        from_ultra = work_launch_url(
            base,
            explicit=f"{base}/ultra/courses/_7949_1/outline/assessment/_241672_1/overview",
        )
        self.assertEqual(from_ultra, expected)
        from_launch = work_launch_url(
            base,
            explicit=(
                f"{base}/webapps/calendar/launch/attempt/"
                "_blackboard.platform.gradebook2.GradableItem-_241672_1"
            ),
            content_id="_241672_1",
            course_id="_7949_1",
        )
        self.assertEqual(from_launch, expected)
        same_course = work_launch_url(
            base, course_id="_7949_1", content_id="_242223_1"
        )
        self.assertIn("content_id=_242223_1", same_course)
        self.assertIn("course_id=_7949_1", same_course)
        reused_column = work_launch_url(
            base, item_id="_92093_1", course_id="_7363_1"
        )
        self.assertNotIn("content_id=_92093_1", reused_column)
        discussion = (
            f"{base}/webapps/discussionboard/do/conference"
            "?action=list_forums&course_id=_7363_1"
            "&nav=discussion_board_entry&content_id=_238570_1"
        )
        self.assertEqual(
            work_launch_url(
                base,
                explicit=discussion,
                content_id="_238570_1",
                course_id="_7363_1",
            ),
            discussion,
        )
        assessment = work_launch_url(
            base,
            course_id="_7363_1",
            content_id="_111_1",
            handler="resource/x-bb-asmt-test-link",
        )
        self.assertIn("/webapps/assessment/take/launchAssessment.jsp", assessment)
        self.assertIn("content_id=_111_1", assessment)
        rewritten = work_launch_url(
            base,
            course_id="_7363_1",
            content_id="_11_1",
            handler="resource/x-bb-forumlink",
            title="Week 2 Discussion",
            explicit=(
                f"{base}/webapps/assignment/uploadAssignment"
                "?content_id=_11_1&course_id=_7363_1&group_id=&mode=view"
            ),
        )
        self.assertIn("discussionboard", rewritten)
        self.assertNotIn("uploadAssignment", rewritten)
        from_title = work_launch_url(
            base,
            course_id="_7363_1",
            content_id="_12_1",
            title="Unit 4 Discussion Forum",
        )
        self.assertIn("discussionboard", from_title)

    def test_content_catalog_uses_crawled_tool_urls(self) -> None:
        from blackboard.api import ContentEntry, apply_content_catalog, parse_html_links
        from blackboard.models import Assignment, Snapshot

        snap = Snapshot(
            assignments=[
                Assignment(
                    id="quiz",
                    course_id="_7363_1",
                    title="Chapter 3 Quiz",
                    content_id="",
                ),
                Assignment(
                    id="forum",
                    course_id="_7363_1",
                    title="Week 2 Discussion",
                    content_id="",
                ),
            ]
        )
        apply_content_catalog(
            snap,
            [
                ContentEntry(
                    course_id="_7363_1",
                    content_id="_10_1",
                    title="Chapter 3 Quiz",
                    handler="resource/x-bb-asmt-test-link",
                    url="https://shs.blackboardchina.cn/webapps/assessment/take/launchAssessment.jsp?course_id=_7363_1&content_id=_10_1",
                ),
                ContentEntry(
                    course_id="_7363_1",
                    content_id="_11_1",
                    title="Week 2 Discussion",
                    handler="resource/x-bb-forumlink",
                    url="https://shs.blackboardchina.cn/webapps/discussionboard/do/conference?action=list_forums&course_id=_7363_1&nav=discussion_board_entry&content_id=_11_1",
                ),
            ],
        )
        self.assertIn("launchAssessment", snap.assignments[0].blackboard_url)
        self.assertEqual(snap.assignments[0].content_handler, "resource/x-bb-asmt-test-link")
        self.assertIn("discussionboard", snap.assignments[1].blackboard_url)
        html = (
            '<a href="/webapps/assessment/take/launchAssessment.jsp'
            '?course_id=_7363_1&content_id=_10_1">Chapter 3 Quiz</a>'
        )
        links = parse_html_links(html)
        self.assertEqual(links[0][1], "Chapter 3 Quiz")
        self.assertIn("launchAssessment", links[0][0])

    def test_calendar_id_is_not_treated_as_content_id(self) -> None:
        data = {
            "results": [
                {
                    "id": "_92093_1",
                    "title": "Spanish Summer Homework",
                    "start": "2026-08-31T14:00:00.000Z",
                    "calendarId": "_7363_1",
                    "itemType": "Assignment",
                }
            ]
        }
        _, assignments = _parse_calendar(
            data, [], "https://shs.blackboardchina.cn"
        )
        self.assertEqual(assignments[0].content_id, "")
        self.assertNotIn("content_id=_92093_1", assignments[0].blackboard_url)

    def test_duplicate_titles_use_newest_or_due_date(self) -> None:
        from datetime import timedelta

        from blackboard.api import apply_column_content_ids
        from blackboard.models import Assignment, Snapshot

        now = datetime.now(timezone.utc)
        snap = Snapshot(
            assignments=[
                Assignment(
                    id="_92093_1",
                    course_id="_7363_1",
                    title="Spanish Summer Homework",
                    due_at=now,
                    content_id="_92093_1",
                )
            ]
        )
        apply_column_content_ids(
            snap,
            "_7363_1",
            [
                ("Spanish Summer Homework", "_92093_1", "_92093_1", now - timedelta(days=365)),
                ("Spanish Summer Homework", "_238000_1", "_238570_1", now),
            ],
        )
        self.assertEqual(snap.assignments[0].content_id, "_238570_1")

    def test_parse_grades_display(self) -> None:
        data = {
            "results": [
                {
                    "id": "g1",
                    "title": "Lab 4",
                    "courseId": "chem",
                    "displayGrade": {"text": "18", "possible": "20"},
                    "posted": "2026-09-01T00:00:00Z",
                }
            ]
        }
        grades = _parse_grades(data, [])
        self.assertEqual(grades[0].score, "18/20")

    def test_soft_http_errors_are_ignored_for_grades(self) -> None:
        from blackboard.api import _is_soft_http_error

        self.assertTrue(
            _is_soft_http_error("HTTP 405 for https://shs.blackboard.cn/learn/api/v1/streams/ultra")
        )
        self.assertFalse(_is_soft_http_error("HTTP 401 for /learn/api/v1/users/me"))

    def test_auth_error_detection(self) -> None:
        self.assertTrue(is_auth_error("HTTP 401 for /learn/api/v1/users/me"))
        self.assertTrue(is_auth_error(ApiRequestError(401, "/learn/api/v1/users/me")))
        self.assertFalse(is_auth_error("HTTP 405 for /learn/api/v1/streams/ultra"))

    def test_profile_401_raises_auth_expired(self) -> None:
        from blackboard.api import fetch_snapshot

        class FakeSession:
            base_url = "https://shs.blackboardchina.cn"

            def _tell(self, message: str, progress: float | None = None) -> None:
                return None

            def get_json(self, path: str):
                raise ApiRequestError(401, path)

        with self.assertRaises(AuthExpiredError):
            fetch_snapshot(FakeSession())  # type: ignore[arg-type]

    def test_store_keeps_snapshot_when_session_expired(self) -> None:
        from unittest.mock import patch

        from blackboard import store as store_mod
        from blackboard.models import Course, Snapshot

        store = Store()
        store.signed_in = True
        store.snapshot = Snapshot(
            user_name="Ada",
            courses=[Course(id="math", name="Math")],
        )

        class FakeSession:
            on_progress = None

        with patch.object(
            store_mod,
            "fetch_snapshot",
            side_effect=AuthExpiredError("HTTP 401 for /learn/api/v1/users/me"),
        ):
            with self.assertRaises(AuthExpiredError):
                store.refresh(FakeSession())  # type: ignore[arg-type]
        self.assertEqual(store.snapshot.user_name, "Ada")
        self.assertEqual(store.snapshot.courses[0].name, "Math")
        self.assertTrue(store.signed_in)


class ColorTests(unittest.TestCase):
    def test_deadline_border_urgency(self) -> None:
        from datetime import timedelta

        from app import theme
        from app.widgets import deadline_border, subject_fill

        now = datetime.now(timezone.utc)
        overdue, width = deadline_border(now - timedelta(hours=2))
        self.assertEqual(overdue, theme.DEADLINE_OVERDUE)
        self.assertGreaterEqual(width, 2.5)

        today, _ = deadline_border(now + timedelta(hours=6))
        self.assertEqual(today, theme.DEADLINE_TODAY)

        later, width = deadline_border(now + timedelta(days=20))
        self.assertEqual(later, theme.DEADLINE_LATER)
        self.assertGreaterEqual(width, 4)

        self.assertEqual(subject_fill("eng"), subject_fill("eng"))
        self.assertNotEqual(subject_fill("eng"), subject_fill("math"))

    def test_countdown_is_accurate_to_the_second(self) -> None:
        from datetime import timedelta

        from app import theme
        from app.widgets import countdown_color, format_countdown

        now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(
            format_countdown(now + timedelta(days=1, hours=2, minutes=3, seconds=4), now=now),
            "Due in 1d 02:03:04",
        )
        self.assertEqual(
            format_countdown(now + timedelta(seconds=9), now=now),
            "Due in 00:00:09",
        )
        self.assertEqual(
            format_countdown(now - timedelta(hours=1, seconds=5), now=now),
            "Overdue 01:00:05",
        )
        self.assertEqual(format_countdown(None, now=now), "")
        self.assertEqual(countdown_color(now - timedelta(seconds=1), now=now), theme.LATE)
        self.assertEqual(countdown_color(now + timedelta(minutes=30), now=now), theme.DEADLINE_TODAY)

    def test_content_tree_keeps_folders_and_files(self) -> None:
        from blackboard.api import content_children, content_nodes_from_items
        from blackboard.models import ContentNode

        items = [
            {
                "id": "_1_1",
                "title": "Week 1",
                "contentHandler": {"id": "resource/x-bb-folder"},
            },
            {
                "id": "_2_1",
                "parentId": "_1_1",
                "title": "Lab notes",
                "fileName": "Lab notes.pdf",
                "size": 2048,
                "modified": "2026-09-01T12:00:00Z",
                "contentHandler": {"id": "resource/x-bb-file"},
            },
        ]
        nodes = content_nodes_from_items(items, "chem", "https://shs.blackboardchina.cn")
        folders = content_children(nodes, "chem", "")
        self.assertEqual([row.title for row in folders], ["Week 1"])
        files = content_children(nodes, "chem", "_1_1")
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].kind, "file")
        self.assertEqual(files[0].filename, "Lab notes.pdf")
        self.assertEqual(files[0].extension, "pdf")
        self.assertEqual(files[0].size_bytes, 2048)
        self.assertIsNotNone(files[0].modified_at)

    def test_format_size_and_content_node_roundtrip(self) -> None:
        from app.widgets import format_size
        from blackboard.models import ContentNode, Snapshot

        self.assertEqual(format_size(0), "—")
        self.assertEqual(format_size(512), "512 B")
        self.assertTrue(format_size(2048).endswith("KB"))
        node = ContentNode(
            id="f1",
            course_id="eng",
            title="Poem",
            filename="Poem.pdf",
            kind="file",
            extension="pdf",
            size_bytes=100,
        )
        snap = Snapshot(content_nodes=[node])
        restored = Snapshot.from_dict(snap.to_dict())
        self.assertEqual(restored.content_nodes[0].filename, "Poem.pdf")
        self.assertEqual(restored.content_nodes[0].size_bytes, 100)


class FilterTests(unittest.TestCase):
    def test_inactivity_hides_stale_courses_but_keeps_assignments(self) -> None:
        from app.filters import sidebar_courses

        store = Store()
        snap = load_sample(store)
        rows = sidebar_courses(snap, query="", inactivity="1w", custom_filter=None)
        names = {course.name for course, hidden in rows if not hidden}
        self.assertIn("English Literature", names)
        self.assertNotIn("Studio Art", names)

        search_rows = sidebar_courses(snap, query="studio", inactivity="1w", custom_filter=None)
        self.assertEqual(len(search_rows), 1)
        self.assertTrue(search_rows[0][1])

        due_ids = {item.course_id for item in snap.assignments}
        self.assertIn("chem", due_ids)
        self.assertIn("math", due_ids)

    def test_assignments_page_includes_calendar_deadlines(self) -> None:
        from blackboard.api import assignments_for
        from blackboard.models import Deadline, Snapshot

        snap = Snapshot(
            deadlines=[
                Deadline(
                    id="d1",
                    title="Lab writeup",
                    when=datetime.now(timezone.utc),
                    course_id="chem",
                    kind="other",
                )
            ]
        )
        items = assignments_for(snap, "all")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Lab writeup")

    def test_search_and_hide_old_late_assignments(self) -> None:
        from datetime import timedelta

        from blackboard.api import assignments_for
        from blackboard.models import Assignment, Course, Grade, Snapshot

        now = datetime.now(timezone.utc)
        snap = Snapshot(
            courses=[Course(id="chem", name="Chemistry")],
            assignments=[
                Assignment(
                    id="old",
                    course_id="chem",
                    title="Old lab",
                    due_at=now - timedelta(days=40),
                    status="late",
                ),
                Assignment(
                    id="new",
                    course_id="chem",
                    title="Recent lab",
                    due_at=now - timedelta(days=2),
                    status="late",
                ),
                Assignment(
                    id="essay",
                    course_id="chem",
                    title="Essay 1",
                    due_at=now + timedelta(days=3),
                    status="todo",
                ),
            ],
        )
        hidden = assignments_for(snap, "all", hide_overdue="1m")
        titles = {item.title for item in hidden}
        self.assertNotIn("Old lab", titles)
        self.assertIn("Recent lab", titles)

        found = assignments_for(snap, "all", query="essay")
        self.assertEqual([item.title for item in found], ["Essay 1"])

    def test_ignored_assignments_leave_main_lists(self) -> None:
        from app.controller import AppController
        from app.views.assignments import visible_assignments
        from blackboard.models import Assignment, Snapshot

        class FakePage:
            controls: list = []

            def update(self) -> None:
                return None

            def run_task(self, handler, *args, **kwargs):
                return None

        ctrl = AppController(FakePage())  # type: ignore[arg-type]
        ctrl.persist = lambda: None  # type: ignore[method-assign]
        ctrl.refresh_assignment_list = lambda: None  # type: ignore[method-assign]
        ctrl.settings = {"ignored_assignments": []}
        ctrl.store.snapshot = Snapshot(
            assignments=[
                Assignment(id="keep", course_id="chem", title="Keep me"),
                Assignment(id="drop", course_id="chem", title="Ignore me"),
            ]
        )
        ctrl.ignore_assignments([ctrl.store.snapshot.assignments[1]])
        visible = visible_assignments(ctrl)
        self.assertEqual([item.id for item in visible], ["keep"])
        ignored = visible_assignments(ctrl, forced_status="ignored")
        self.assertEqual([item.id for item in ignored], ["drop"])

    def test_mark_assignment_submitted_is_saved(self) -> None:
        from datetime import timedelta

        from app.controller import AppController
        from app.views.assignments import visible_assignments
        from blackboard.models import Assignment, Snapshot

        class FakePage:
            controls: list = []

            def update(self) -> None:
                return None

            def run_task(self, handler, *args, **kwargs):
                return None

        now = datetime.now(timezone.utc)
        ctrl = AppController(FakePage())  # type: ignore[arg-type]
        persisted: list = []

        def persist() -> None:
            persisted.append(list(ctrl.settings.get("marked_submitted_assignments") or []))

        ctrl.persist = persist  # type: ignore[method-assign]
        ctrl.rebuild = lambda: None  # type: ignore[method-assign]
        ctrl.refresh_assignment_list = lambda: None  # type: ignore[method-assign]
        ctrl.settings = {
            "ignored_assignments": [],
            "marked_submitted_assignments": [],
            "hide_filtered_assignments": False,
            "inactivity": "all",
        }
        item = Assignment(
            id="lab",
            course_id="chem",
            title="Lab 5",
            due_at=now + timedelta(days=2),
            status="todo",
        )
        ctrl.store.snapshot = Snapshot(assignments=[item])
        ctrl.mark_assignments_submitted([item])
        self.assertTrue(ctrl.is_marked_submitted(item))
        self.assertEqual(persisted[-1][0]["id"], "lab")
        self.assertEqual(
            [row.id for row in visible_assignments(ctrl, forced_status="submitted")],
            ["lab"],
        )
        self.assertEqual(visible_assignments(ctrl, forced_status="todo"), [])

        ctrl.unmark_assignments_submitted([item])
        self.assertFalse(ctrl.is_marked_submitted(item))
        self.assertEqual(persisted[-1], [])
        self.assertEqual(
            [row.id for row in visible_assignments(ctrl, forced_status="todo")],
            ["lab"],
        )

    def test_marked_submitted_survives_new_snapshot(self) -> None:
        from datetime import timedelta

        from app.controller import AppController
        from blackboard.api import _resolve_assignment_status
        from blackboard.models import Assignment, Snapshot

        class FakePage:
            controls: list = []

            def update(self) -> None:
                return None

            def run_task(self, handler, *args, **kwargs):
                return None

        now = datetime.now(timezone.utc)
        ctrl = AppController(FakePage())  # type: ignore[arg-type]
        ctrl.persist = lambda: None  # type: ignore[method-assign]
        ctrl.rebuild = lambda: None  # type: ignore[method-assign]
        ctrl.refresh_assignment_list = lambda: None  # type: ignore[method-assign]
        ctrl.settings = {
            "marked_submitted_assignments": [
                {"id": "lab", "course_id": "chem", "title": "Lab 5"}
            ]
        }
        refreshed = Assignment(
            id="lab",
            course_id="chem",
            title="Lab 5",
            due_at=now + timedelta(days=2),
            status="todo",
        )
        ctrl.store.snapshot = Snapshot(assignments=[refreshed])
        ctrl._sync_manual_submitted()
        self.assertEqual(_resolve_assignment_status(ctrl.store.snapshot, refreshed), "submitted")
        self.assertEqual(refreshed.status, "submitted")

    def test_all_page_lists_submitted_after_unsubmitted(self) -> None:
        from datetime import timedelta

        from app.controller import AppController
        from app.views.assignments import visible_assignments
        from blackboard.models import Assignment, Snapshot

        class FakePage:
            controls: list = []

            def update(self) -> None:
                return None

            def run_task(self, handler, *args, **kwargs):
                return None

        now = datetime.now(timezone.utc)
        ctrl = AppController(FakePage())  # type: ignore[arg-type]
        ctrl.persist = lambda: None  # type: ignore[method-assign]
        ctrl.assignment_filter = "all"
        ctrl.settings = {
            "ignored_assignments": [],
            "hide_filtered_assignments": False,
            "inactivity": "all",
        }
        ctrl.store.snapshot = Snapshot(
            assignments=[
                Assignment(
                    id="done-soon",
                    course_id="chem",
                    title="Submitted soon",
                    due_at=now + timedelta(days=1),
                    status="submitted",
                    has_attempt=True,
                ),
                Assignment(
                    id="todo-later",
                    course_id="chem",
                    title="Todo later",
                    due_at=now + timedelta(days=5),
                    status="todo",
                ),
            ]
        )
        ids = [item.id for item in visible_assignments(ctrl)]
        self.assertEqual(ids, ["todo-later", "done-soon"])

    def test_grade_marks_assignment_submitted(self) -> None:
        from blackboard.api import _apply_assignment_status
        from blackboard.models import Assignment, Grade, Snapshot

        snap = Snapshot(
            assignments=[
                Assignment(id="a1", course_id="chem", title="Lab 4", status="todo"),
            ],
            grades=[
                Grade(id="g1", course_id="chem", title="Lab 4", score="18/20"),
            ],
        )
        _apply_assignment_status(snap)
        self.assertEqual(snap.assignments[0].status, "submitted")

    def test_submitted_work_is_not_marked_late(self) -> None:
        from datetime import timedelta

        from blackboard.api import assignments_for
        from blackboard.models import Assignment, Grade, Snapshot

        now = datetime.now(timezone.utc)
        snap = Snapshot(
            assignments=[
                Assignment(
                    id="_99_1",
                    course_id="chem",
                    title="Lab 5: Titration report",
                    due_at=now - timedelta(days=3),
                    status="late",
                ),
                Assignment(
                    id="plain",
                    course_id="math",
                    title="Old quiz",
                    due_at=now - timedelta(days=3),
                    status="late",
                ),
            ],
            grades=[
                Grade(id="_99_1", course_id="other", title="Something else", score="Needs grading"),
                Grade(id="g2", course_id="chem", title="Lab 5 Titration report", score="16/20"),
            ],
        )
        items = {item.id: item.status for item in assignments_for(snap, "all")}
        self.assertEqual(items["_99_1"], "submitted")
        self.assertEqual(items["plain"], "late")

    def test_grade_page_hides_unsubmitted_and_splits_folders(self) -> None:
        from blackboard.api import grade_page_groups
        from blackboard.models import Assignment, Grade, Snapshot

        snap = Snapshot(
            assignments=[
                Assignment(id="todo", course_id="chem", title="Not started", status="todo"),
                Assignment(
                    id="late",
                    course_id="chem",
                    title="Missing lab",
                    status="late",
                ),
                Assignment(
                    id="waiting",
                    course_id="chem",
                    title="Lab 5 report",
                    status="submitted",
                    has_attempt=True,
                ),
            ],
            grades=[
                Grade(id="g1", course_id="chem", title="Lab 4", score="18/20"),
                Grade(id="g2", course_id="chem", title="Draft", score="Submitted"),
                Grade(id="g3", course_id="chem", title="Empty column", score="-"),
            ],
        )
        graded, pending = grade_page_groups(snap)
        self.assertEqual([row.title for row in graded], ["Lab 4"])
        self.assertEqual(
            {row.title for row in pending},
            {"Draft", "Lab 5 report"},
        )
        hidden = {row.title for row in graded + pending}
        self.assertNotIn("Not started", hidden)
        self.assertNotIn("Missing lab", hidden)
        self.assertNotIn("Empty column", hidden)

    def test_review_history_html_counts_as_submitted(self) -> None:
        from datetime import timedelta
        from pathlib import Path

        from blackboard.api import assignments_for, html_indicates_submission
        from blackboard.models import Assignment, Snapshot

        submitted_page = """
        <title>复查提交历史记录: Spanish Summer Homework</title>
        <span id="pageTitleText">复查提交历史记录: Spanish Summer Homework</span>
        <div id="currentAttempt">
          <span class="subHeader dateStamp">26-8-23 下午4:18</span>
          <ul id="currentAttempt_submissionList" class="filesList">
            <a id="currentAttempt_attemptFile_771635_1" class="attachment genericFile">CamScanner 8-23-26 16.16.pdf</a>
            <a href="/webapps/assignment/download?course_id=_7363_1&amp;attempt_id=_737513_1&amp;file_id=_771635_1"></a>
          </ul>
        </div>
        """
        upload_page = """
        <title>上传作业: Spanish Summer Homework</title>
        <span id="pageTitleText">上传作业: Spanish Summer Homework</span>
        <form id="uploadAssignmentForm"><input name="newFile_fileId"></form>
        """
        self.assertTrue(html_indicates_submission(submitted_page))
        self.assertFalse(html_indicates_submission(upload_page))

        saved = Path(
            r"c:\Users\Hank\Downloads\复查提交历史记录_ Spanish Summer Homework – 2025-2026 G10-11 ....html"
        )
        if saved.is_file():
            self.assertTrue(html_indicates_submission(saved.read_text(encoding="utf-8", errors="ignore")))

        now = datetime.now(timezone.utc)
        snap = Snapshot(
            assignments=[
                Assignment(
                    id="spanish",
                    course_id="_7363_1",
                    title="Spanish Summer Homework",
                    due_at=now - timedelta(days=5),
                    status="late",
                    has_attempt=True,
                )
            ]
        )
        self.assertEqual(assignments_for(snap, "all")[0].status, "submitted")

    def test_empty_grade_column_does_not_count_as_submitted(self) -> None:
        from datetime import timedelta

        from blackboard.api import assignments_for
        from blackboard.models import Assignment, Grade, Snapshot

        now = datetime.now(timezone.utc)
        snap = Snapshot(
            assignments=[
                Assignment(
                    id="missed",
                    course_id="chem",
                    title="Lab 6",
                    due_at=now - timedelta(days=2),
                    status="late",
                )
            ],
            grades=[
                Grade(id="col", course_id="chem", title="Lab 6", score=""),
            ],
        )
        items = assignments_for(snap, "all")
        self.assertEqual(items[0].status, "late")

    def test_custom_whitelist(self) -> None:
        from app.filters import sidebar_courses

        store = Store()
        snap = load_sample(store)
        custom = {"id": "stem", "name": "STEM", "course_ids": ["math", "chem"]}
        rows = sidebar_courses(snap, query="", inactivity="all", custom_filter=custom)
        ids = {course.id for course, hidden in rows if not hidden}
        self.assertEqual(ids, {"math", "chem"})

    def test_hide_assignments_outside_filter(self) -> None:
        from app.controller import AppController
        from app.views.assignments import visible_assignments
        from blackboard.models import Assignment, Course, Snapshot

        class FakePage:
            controls: list = []

            def update(self) -> None:
                return None

            def run_task(self, handler, *args, **kwargs):
                return None

        ctrl = AppController(FakePage())  # type: ignore[arg-type]
        ctrl.persist = lambda: None  # type: ignore[method-assign]
        ctrl.refresh_assignment_list = lambda: None  # type: ignore[method-assign]
        ctrl.store.snapshot = Snapshot(
            courses=[
                Course(id="math", name="Math"),
                Course(id="chem", name="Chem"),
                Course(id="art", name="Art"),
            ],
            assignments=[
                Assignment(id="m1", course_id="math", title="Quiz"),
                Assignment(id="a1", course_id="art", title="Sketch"),
            ],
        )
        ctrl.settings = {
            "ignored_assignments": [],
            "hide_filtered_assignments": False,
            "custom_filters": [{"id": "stem", "name": "STEM", "course_ids": ["math", "chem"]}],
            "active_custom_filter": "stem",
            "inactivity": "all",
        }
        shown = {item.id for item in visible_assignments(ctrl)}
        self.assertEqual(shown, {"m1", "a1"})
        ctrl.settings["hide_filtered_assignments"] = True
        shown = {item.id for item in visible_assignments(ctrl)}
        self.assertEqual(shown, {"m1"})

    def test_next_launch_remembers_filter_course_ids(self) -> None:
        from app.controller import AppController
        from blackboard.models import Course, Snapshot

        class FakePage:
            controls: list = []

            def update(self) -> None:
                return None

            def run_task(self, handler, *args, **kwargs):
                return None

        ctrl = AppController(FakePage())  # type: ignore[arg-type]
        ctrl.persist = lambda: None  # type: ignore[method-assign]
        ctrl.refresh_course_list = lambda: None  # type: ignore[method-assign]
        ctrl.store.snapshot = Snapshot(
            courses=[
                Course(id="math", name="Math"),
                Course(id="art", name="Art"),
            ]
        )
        ctrl.settings = {
            "custom_filters": [{"id": "stem", "name": "STEM", "course_ids": ["math"]}],
            "active_custom_filter": "stem",
            "inactivity": "all",
            "load_filter_courses_only": False,
            "load_course_ids": [],
        }
        self.assertIsNone(ctrl.fetch_course_ids())
        ctrl.set_load_filter_courses_only(True)
        self.assertEqual(ctrl.fetch_course_ids(), {"math"})

    def test_refresh_opens_loading_page(self) -> None:
        import threading

        from app.controller import AppController

        class FakePage:
            controls: list = []

            def update(self) -> None:
                return None

            def run_task(self, handler, *args, **kwargs):
                return None

        class FakeSession:
            is_open = True

            def confirm_login(self) -> bool:
                return True

        started = threading.Event()
        release = threading.Event()
        ctrl = AppController(FakePage())  # type: ignore[arg-type]
        ctrl.store.signed_in = True
        ctrl.session = FakeSession()  # type: ignore[assignment]
        ctrl.route = "/grades"
        ctrl._ui_thread = threading.current_thread()

        def fake_refresh(*args, **kwargs):
            started.set()
            release.wait(timeout=2)

        ctrl.store.refresh = fake_refresh  # type: ignore[method-assign]
        ctrl.refresh()
        self.assertTrue(started.wait(timeout=2))
        self.assertEqual(ctrl.route, "/loading")
        self.assertEqual(ctrl.loading_kind, "refresh")
        ctrl.cancel_loading()
        self.assertEqual(ctrl.route, "/grades")
        self.assertFalse(ctrl.busy)
        release.set()

    def test_refresh_relogs_in_when_session_expired(self) -> None:
        import threading
        import time

        from app.controller import AppController
        from blackboard.models import Course, Snapshot

        class FakePage:
            controls: list = []

            def update(self) -> None:
                return None

            def run_task(self, handler, *args, **kwargs):
                return None

        class FakeSession:
            is_open = True
            base_url = "https://shs.blackboardchina.cn"

            def confirm_login(self) -> bool:
                return False

            def login_with_credentials(self, username: str, password: str, timeout_sec: float = 90) -> bool:
                self.logged_in_as = (username, password)
                return True

            def prepare_origin(self) -> None:
                return None

        ctrl = AppController(FakePage())  # type: ignore[arg-type]
        ctrl.store.signed_in = True
        ctrl.store.snapshot = Snapshot(
            user_name="Ada",
            courses=[Course(id="math", name="Math")],
        )
        ctrl.session = FakeSession()  # type: ignore[assignment]
        ctrl.route = "/home"
        ctrl.login_username = "student"
        ctrl._login_password = "secret"
        ctrl.persist = lambda: None  # type: ignore[method-assign]
        ctrl._ui_thread = threading.current_thread()
        refreshed = threading.Event()

        def fake_refresh(*args, **kwargs):
            refreshed.set()
            return ctrl.store.snapshot

        ctrl.store.refresh = fake_refresh  # type: ignore[method-assign]
        ctrl.refresh()
        self.assertTrue(refreshed.wait(timeout=2))
        deadline = time.time() + 2
        while ctrl.busy and time.time() < deadline:
            time.sleep(0.02)
        self.assertFalse(ctrl.busy)
        self.assertEqual(ctrl.session.logged_in_as, ("student", "secret"))  # type: ignore[attr-defined]
        self.assertEqual(ctrl.route, "/home")
        self.assertTrue(ctrl.store.signed_in)
        self.assertEqual(ctrl._login_password, "secret")

    def test_refresh_retries_after_expired_fetch(self) -> None:
        import threading
        import time

        from app.controller import AppController
        from blackboard.auth import AuthExpiredError
        from blackboard.models import Snapshot

        class FakePage:
            controls: list = []

            def update(self) -> None:
                return None

            def run_task(self, handler, *args, **kwargs):
                return None

        class FakeSession:
            is_open = True
            base_url = "https://shs.blackboardchina.cn"

            def confirm_login(self) -> bool:
                return True

            def login_with_credentials(self, username: str, password: str, timeout_sec: float = 90) -> bool:
                self.relogged = True
                return True

            def prepare_origin(self) -> None:
                return None

        ctrl = AppController(FakePage())  # type: ignore[arg-type]
        ctrl.store.signed_in = True
        ctrl.store.snapshot = Snapshot(user_name="Ada")
        ctrl.session = FakeSession()  # type: ignore[assignment]
        ctrl.route = "/home"
        ctrl.login_username = "student"
        ctrl._login_password = "secret"
        ctrl.persist = lambda: None  # type: ignore[method-assign]
        ctrl._ui_thread = threading.current_thread()
        calls = {"n": 0}
        done = threading.Event()

        def fake_refresh(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise AuthExpiredError("HTTP 401 for /learn/api/v1/users/me")
            done.set()
            return ctrl.store.snapshot

        ctrl.store.refresh = fake_refresh  # type: ignore[method-assign]
        ctrl.refresh()
        self.assertTrue(done.wait(timeout=2))
        deadline = time.time() + 2
        while ctrl.busy and time.time() < deadline:
            time.sleep(0.02)
        self.assertFalse(ctrl.busy)
        self.assertEqual(calls["n"], 2)
        self.assertTrue(getattr(ctrl.session, "relogged", False))
        self.assertEqual(ctrl.route, "/home")

    def test_refresh_prompts_login_when_password_missing(self) -> None:
        import threading
        import time

        from app.controller import AppController
        from blackboard.models import Course, Snapshot

        class FakePage:
            controls: list = []

            def update(self) -> None:
                return None

            def run_task(self, handler, *args, **kwargs):
                return None

        class FakeSession:
            is_open = True

            def confirm_login(self) -> bool:
                return False

            def login_with_credentials(self, *args, **kwargs):
                raise AssertionError("should not attempt login without a password")

        ctrl = AppController(FakePage())  # type: ignore[arg-type]
        ctrl.store.signed_in = True
        ctrl.store.snapshot = Snapshot(
            user_name="Ada",
            courses=[Course(id="math", name="Math")],
        )
        ctrl.session = FakeSession()  # type: ignore[assignment]
        ctrl.route = "/home"
        ctrl.login_username = "student"
        ctrl._login_password = ""
        ctrl._ui_thread = threading.current_thread()
        ctrl.refresh()
        deadline = time.time() + 2
        while ctrl.busy and time.time() < deadline:
            time.sleep(0.02)
        self.assertFalse(ctrl.busy)
        self.assertEqual(ctrl.route, "/login")
        self.assertIn("expired", ctrl.login_message.lower())
        self.assertEqual(ctrl.store.snapshot.user_name, "Ada")
        self.assertFalse(ctrl.store.signed_in)

    def test_logout_clears_password(self) -> None:
        from app.controller import AppController

        class FakePage:
            controls: list = []

            def update(self) -> None:
                return None

            def run_task(self, handler, *args, **kwargs):
                return None

        ctrl = AppController(FakePage())  # type: ignore[arg-type]
        ctrl._login_password = "secret"
        ctrl.store.signed_in = True
        ctrl.logout()
        self.assertEqual(ctrl._login_password, "")
        self.assertEqual(ctrl.route, "/login")

    def test_settings_never_store_password(self) -> None:
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from blackboard import store as store_mod
        from blackboard.store import save_settings

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            with patch.object(store_mod, "SETTINGS_PATH", path), patch.object(
                store_mod, "DATA_DIR", Path(tmp)
            ):
                save_settings(
                    {
                        "username": "student",
                        "password": "should-not-be-saved",
                        "base_url": "https://shs.blackboardchina.cn",
                        "marked_submitted_assignments": [
                            {"id": "a1", "course_id": "chem", "title": "Lab 5"}
                        ],
                    }
                )
            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["username"], "student")
        self.assertNotIn("password", data)
        self.assertEqual(data["marked_submitted_assignments"][0]["id"], "a1")

    def test_start_login_requires_credentials(self) -> None:
        from app.controller import AppController

        class FakePage:
            controls: list = []

            def update(self) -> None:
                return None

            def run_task(self, handler, *args, **kwargs):
                return None

        ctrl = AppController(FakePage())  # type: ignore[arg-type]
        ctrl.persist = lambda: None  # type: ignore[method-assign]
        ctrl.start_login("", "")
        self.assertEqual(ctrl.login_status, "failed")
        self.assertIn("required", ctrl.login_message.lower())

    def test_installer_layout_skips_first_run_shortcut_prompt(self) -> None:
        import tempfile
        from pathlib import Path

        from app.branding import SETUP_MARKER
        from app.controller import AppController
        from app.shortcuts import installed_by_setup

        class FakePage:
            controls: list = []

            def update(self) -> None:
                return None

            def run_task(self, handler, *args, **kwargs):
                return None

            def show_dialog(self, dialog) -> None:
                raise AssertionError("installer copies should not prompt for shortcuts")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(installed_by_setup(root))
            (root / SETUP_MARKER).write_text("installed", encoding="utf-8")
            self.assertTrue(installed_by_setup(root))

        ctrl = AppController(FakePage())  # type: ignore[arg-type]
        ctrl.settings["shortcut_prompt_done"] = False
        from unittest.mock import patch

        with patch("app.shortcuts.installed_by_setup", return_value=True), patch(
            "app.shortcuts.is_packaged", return_value=True
        ):
            ctrl.maybe_prompt_shortcuts()
        self.assertFalse(ctrl._shortcut_prompt_shown)


class ViewBuilderTests(unittest.TestCase):
    def test_views_build_with_sample_snapshot(self) -> None:
        import flet as ft

        from app.controller import AppController
        from app.views.assignment_detail import build_assignment_detail
        from app.views.assignments import build_assignments, build_ignored, build_submitted
        from app.views.calendar_view import build_calendar
        from app.views.course_detail import build_course_detail
        from app.views.courses import build_courses
        from app.views.contents import build_contents
        from app.views.grades import build_grades
        from app.views.home import build_home
        from app.views.loading import build_loading
        from app.views.login import build_login
        from app.views.settings import build_settings
        from app.views.course_sidebar import build_course_sidebar
        from app.views.shell import build_shell

        class FakePage:
            controls: list = []

            def update(self) -> None:
                return None

            def run_task(self, handler, *args, **kwargs):
                return None

            def show_dialog(self, dialog) -> None:
                return None

            def pop_dialog(self):
                return None

        store = Store()
        snap = load_sample(store)
        self.assertTrue(store.signed_in)
        self.assertGreaterEqual(len(snap.courses), 3)
        self.assertTrue(upcoming(snap, 14))

        ctrl = AppController(FakePage())  # type: ignore[arg-type]
        ctrl.store = store
        ctrl.route = "/home"
        for builder in (
            lambda: build_login(ctrl),
            lambda: build_loading(ctrl),
            lambda: build_home(ctrl),
            lambda: build_courses(ctrl),
            lambda: build_course_detail(ctrl, "eng"),
            lambda: build_assignments(ctrl),
            lambda: build_submitted(ctrl),
            lambda: build_ignored(ctrl),
            lambda: build_assignment_detail(ctrl, "a1"),
            lambda: build_grades(ctrl),
            lambda: build_contents(ctrl),
            lambda: build_calendar(ctrl),
            lambda: build_settings(ctrl),
            lambda: build_shell(ctrl),
            lambda: build_course_sidebar(ctrl),
        ):
            control = builder()
            self.assertIsInstance(control, ft.Control)

        ctrl.settings["contents_view_mode"] = "folder"
        ctrl.contents_path = []
        self.assertIsInstance(build_contents(ctrl), ft.Control)
        ctrl.contents_path = ["course:eng"]
        self.assertIsInstance(build_contents(ctrl), ft.Control)
        ctrl.contents_path = ["course:eng", "eng-readings"]
        self.assertIsInstance(build_contents(ctrl), ft.Control)

        ctrl.settings["contents_view_mode"] = "columns"
        ctrl.contents_path = []
        self.assertIsInstance(build_contents(ctrl), ft.Control)
        ctrl.contents_path = ["course:eng", "eng-readings"]
        self.assertIsInstance(build_contents(ctrl), ft.Control)
        ctrl.contents_path = ["course:eng", "eng-readings", "nested", "deeper"]
        self.assertIsInstance(build_contents(ctrl), ft.Control)


class ContentsNavTests(unittest.TestCase):
    def test_miller_columns_cap_at_three(self) -> None:
        from app.contents_nav import miller_columns, path_after_open

        self.assertEqual(miller_columns([]), [(None, None)])
        self.assertEqual(miller_columns(["A"]), [(None, "A"), ("A", None)])
        self.assertEqual(
            miller_columns(["A", "B"]),
            [(None, "A"), ("A", "B"), ("B", None)],
        )
        self.assertEqual(
            miller_columns(["A", "B", "C"]),
            [("A", "B"), ("B", "C"), ("C", None)],
        )
        self.assertEqual(
            miller_columns(["A", "B", "C", "D"]),
            [("B", "C"), ("C", "D"), ("D", None)],
        )

        self.assertEqual(path_after_open([], None, "A"), ["A"])
        self.assertEqual(path_after_open(["A", "B", "C"], "A", "X"), ["A", "X"])
        self.assertEqual(path_after_open(["A"], "A", "B"), ["A", "B"])

    def test_explorer_items_sample_tree(self) -> None:
        from app.contents_nav import explorer_items

        store = Store()
        snap = load_sample(store)
        roots = explorer_items(snap.courses, snap.content_nodes, None)
        self.assertTrue(any(item.key == "course:eng" for item in roots))
        readings = explorer_items(snap.courses, snap.content_nodes, "eng-readings")
        names = {item.name for item in readings}
        self.assertIn("Sonnet 18.pdf", names)
        self.assertFalse(any(item.is_folder for item in readings))


class HomeAndLoadingTests(unittest.TestCase):
    def test_format_loading_message_ellipsizes_long_course_names(self) -> None:
        from app.widgets import format_loading_message

        short = "Indexing 3 of 12: Chemistry"
        self.assertEqual(format_loading_message(short), short)
        long_name = "Indexing 3 of 12: " + ("Shanghai High School Very Long Course Title " * 3)
        clipped = format_loading_message(long_name)
        self.assertTrue(clipped.endswith("…"))
        self.assertLessEqual(len(clipped), 48)
        self.assertTrue(clipped.startswith("Indexing 3 of 12:"))

    def test_home_hides_submitted_deadlines_even_when_overdue(self) -> None:
        from datetime import timedelta

        from blackboard.api import deadline_is_finished, upcoming
        from blackboard.models import Assignment, Deadline, Grade, Snapshot

        now = datetime.now(timezone.utc)
        snap = Snapshot(
            assignments=[
                Assignment(
                    id="done",
                    course_id="chem",
                    title="Lab 5 report",
                    due_at=now - timedelta(days=1),
                    status="late",
                ),
                Assignment(
                    id="open",
                    course_id="eng",
                    title="Essay 3",
                    due_at=now + timedelta(days=1),
                    status="todo",
                ),
            ],
            grades=[
                Grade(
                    id="g1",
                    course_id="chem",
                    title="Lab 5 report",
                    score="Needs grading",
                ),
            ],
            deadlines=[
                Deadline(
                    id="cal-done",
                    title="Lab 5 report",
                    when=now - timedelta(hours=2),
                    course_id="chem",
                    kind="assignment",
                    assignment_id="cal-done",
                ),
                Deadline(
                    id="open",
                    title="Essay 3",
                    when=now + timedelta(days=1),
                    course_id="eng",
                    kind="assignment",
                    assignment_id="open",
                ),
            ],
        )
        visible = [
            item.id
            for item in upcoming(snap, 7)
            if not deadline_is_finished(snap, item)
        ]
        self.assertEqual(visible, ["open"])
        self.assertTrue(deadline_is_finished(snap, snap.deadlines[0]))


if __name__ == "__main__":
    unittest.main()
