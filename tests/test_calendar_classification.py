import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from blackboard import api
from blackboard.models import Assignment, ContentNode, Course, Deadline, Snapshot

BASE = 'https://school.example'
COURSE = '_1_1'
PAGE = BASE + '/webapps/assignment/uploadAssignment?course_id=_1_1&content_id=_2_1'
DUE = datetime(2099, 1, 1, tzinfo=timezone.utc)


class CalendarClassificationTests(unittest.TestCase):
    def test_submission_page_overrides_event_type_and_title(self):
        for title in ('Final Exam Review', 'Practice questions', 'Office hours', 'Project'):
            for url in (PAGE, '/webapps/assessment/take/launchAssessment.jsp?course_id=_1_1&content_id=_2_1',
                        '/ultra/courses/_1_1/outline/assessment/_2_1/overview',
                        '/webapps/calendar/launch/attempt/_3_1'):
                with self.subTest(title=title, url=url):
                    raw = dict(id='event', title=title, type='CourseEvent', courseId=COURSE,
                               launchUrl=url, startDate=DUE.isoformat())
                    deadlines, assignments = api._parse_calendar([raw], [Course(COURSE, 'Course')], BASE)
                    self.assertEqual(deadlines[0].kind, 'assignment')
                    self.assertEqual(deadlines[0].assignment_id, assignments[0].id)
                    snapshot = Snapshot(deadlines=deadlines, assignments=assignments)
                    api._apply_launch_urls(snapshot, BASE)
                    self.assertEqual(deadlines[0].kind, 'assignment')
                    self.assertEqual(len(snapshot.assignments), 1)

    def test_submission_handler_overrides_event_labels(self):
        for handler in ('resource/x-bb-assignment', 'resource/x-bb-asmt-test-link', 'resource/x-bb-forumlink'):
            with self.subTest(handler=handler):
                self.assertEqual(api._deadline_kind(dict(title='Final exam', type='event',
                                 contentHandler={'id': handler})), 'assignment')

    def test_deep_event_links_and_files_are_not_submission_pages(self):
        for url in ('/webapps/collab-ultra/launch', '/webapps/blackboard/execute/launcher?type=Course&id=_1_1',
                    '/webapps/blackboard/content/listContent.jsp?course_id=_1_1&content_id=_2_1',
                    '/webapps/assignment/download?attempt_id=_3_1', '/ultra/courses/_1_1/outline'):
            with self.subTest(url=url):
                deadlines, assignments = api._parse_calendar([dict(id='event', title='Meeting',
                    type='CourseEvent', courseId=COURSE, url=url)], [Course(COURSE, 'Course')], BASE)
                snapshot = Snapshot(deadlines=deadlines, assignments=assignments)
                api._apply_launch_urls(snapshot, BASE)
                self.assertEqual(snapshot.deadlines[0].kind, 'other')
                self.assertEqual(snapshot.assignments, [])

    def test_catalog_discovers_submission_for_previously_event_only_item(self):
        deadline = Deadline('event', 'Final Exam Review', DUE, COURSE)
        snapshot = Snapshot(deadlines=[deadline])
        catalog = [api.ContentEntry(COURSE, '_2_1', deadline.title, 'resource/x-bb-assignment', PAGE)]
        api.apply_content_catalog(snapshot, catalog)
        api._apply_launch_urls(snapshot, BASE)
        api.apply_content_catalog(snapshot, catalog)
        self.assertEqual(deadline.kind, 'assignment')
        self.assertEqual(deadline.blackboard_url, PAGE)
        self.assertEqual(deadline.assignment_id, snapshot.assignments[0].id)
        self.assertEqual(len(snapshot.assignments), 1)

    def test_repeated_titles_keep_distinct_submission_pages(self):
        deadlines = [Deadline('first', 'Review', DUE, COURSE, blackboard_url=PAGE),
                     Deadline('second', 'Review', DUE, COURSE,
                              blackboard_url=PAGE.replace('_2_1', '_3_1'))]
        snapshot = Snapshot(deadlines=deadlines)
        api._apply_launch_urls(snapshot, BASE)
        api._apply_launch_urls(snapshot, BASE)
        self.assertEqual(len(snapshot.assignments), 2)
        self.assertEqual([item.assignment_id for item in deadlines], ['first', 'second'])
        self.assertEqual(snapshot.assignment_by_id('first').blackboard_url, PAGE)
        self.assertEqual(snapshot.assignment_by_id('second').blackboard_url, PAGE.replace('_2_1', '_3_1'))

    def test_unrelated_coursework_does_not_promote_event_with_content_id(self):
        deadline = Deadline('event', 'Meeting', DUE, COURSE, content_id='_99_1')
        snapshot = Snapshot(deadlines=[deadline])
        api.apply_content_catalog(snapshot, [api.ContentEntry(COURSE, '_2_1', 'Project',
                                  'resource/x-bb-assignment', PAGE)])
        self.assertEqual(deadline.kind, 'other')
        self.assertEqual(snapshot.assignments, [])

    def test_assignment_remains_in_calendar_sync_when_events_are_hidden(self):
        import app.google_calendar as google
        deadline = Deadline('event', 'Final Exam Review', DUE, COURSE, blackboard_url=PAGE)
        snapshot = Snapshot(deadlines=[deadline])
        api._apply_launch_urls(snapshot, BASE)
        with patch('blackboard.store.load_settings', return_value={}):
            events = google.events_for_sync(snapshot, base_url=BASE, hide_other=True)
        self.assertEqual(len(events), 1)
        self.assertIn('Assignment', events[0]['description'])

    def test_same_title_in_another_course_does_not_promote_event(self):
        deadline = Deadline('event', 'Final Exam Review', DUE, COURSE)
        snapshot = Snapshot(deadlines=[deadline])
        api.apply_content_catalog(snapshot, [api.ContentEntry('_99_1', '_2_1', deadline.title,
                                  'resource/x-bb-assignment', PAGE)])
        self.assertEqual(deadline.kind, 'other')
        self.assertEqual(snapshot.assignments, [])

    def test_enriched_assignment_promotes_matching_calendar_entry_preserving_status(self):
        deadline = Deadline('event', 'Review', DUE, COURSE)
        assignment = Assignment('work', COURSE, 'Review', due_at=DUE, status='submitted',
                                blackboard_url=PAGE, has_attempt=True)
        snapshot = Snapshot(deadlines=[deadline], assignments=[assignment])
        api._apply_launch_urls(snapshot, BASE)
        self.assertEqual(deadline.kind, 'assignment')
        self.assertEqual(deadline.assignment_id, 'work')
        self.assertEqual(len(snapshot.assignments), 1)
        self.assertTrue(api.deadline_is_finished(snapshot, deadline))
        self.assertEqual(assignment.status, 'submitted')

    def test_saved_calendar_is_repaired_from_its_links_or_content_index(self):
        import data
        import present
        import blackboard.store as storage
        for direct in (True, False):
            with self.subTest(direct=direct), tempfile.TemporaryDirectory() as folder:
                snapshot = Snapshot(deadlines=[Deadline('event', 'Final Exam Review', DUE, COURSE,
                                    blackboard_url=PAGE if direct else '')])
                if not direct:
                    snapshot.content_nodes = [ContentNode('_2_1', COURSE, title='Final Exam Review',
                        kind='link', handler='resource/x-bb-assignment', open_url=PAGE)]
                path = Path(folder) / 'snapshot.json'
                from persistence import write_json
                write_json(path, snapshot.to_dict())
                with patch.object(data, 'SNAPSHOT_PATH', path), patch.object(storage, 'SNAPSHOT_PATH', path):
                    loaded = present.load_snapshot()
                    self.assertEqual(loaded.deadlines[0].kind, 'assignment')
                    with patch.object(present, 'load_settings', return_value={}), patch.object(present, 'load_account', return_value={}):
                        state = present._build_state(loaded)
                    self.assertEqual(state['calendar'][0]['kind'], 'assignment')
                    self.assertEqual(len(state['assignments']), 1)
                    store = storage.Store()
                    self.assertTrue(store.load_cache())
                    self.assertEqual(store.snapshot.deadlines[0].kind, 'assignment')
