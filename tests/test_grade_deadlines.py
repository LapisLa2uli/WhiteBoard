import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import present
from blackboard.models import Assignment, Course, Grade, Snapshot


class GradeDeadlineTests(unittest.TestCase):
    def test_deadlines_use_course_scoped_assignments_not_posted_dates(self):
        due = datetime(2026, 10, 1, tzinfo=timezone.utc)
        posted = datetime(2026, 10, 8, tzinfo=timezone.utc)
        snapshot = Snapshot(courses=[Course('c', 'Course'), Course('other', 'Other')], assignments=[
            Assignment('a', 'c', 'Renamed essay', due_at=due, content_id='content'),
            Assignment('b', 'c', 'Title match', due_at=due),
            Assignment('p', 'c', 'Pending', due_at=due, status='submitted'),
            Assignment('u', 'c', 'Undated'),
            Assignment('x', 'c', 'Duplicate', due_at=due),
            Assignment('y', 'c', 'Duplicate', due_at=posted),
            Assignment('a', 'other', 'Other course', due_at=posted),
        ], grades=[
            Grade('g1', 'c', 'Essay', score='8', posted_at=posted, assignment_id='a'),
            Grade('g2', 'c', 'Content match', score='8', assignment_id='content'),
            Grade('g3', 'c', ' TITLE   MATCH ', score='8'),
            Grade('g4', 'c', 'Unknown', score='8', posted_at=posted),
            Grade('g5', 'c', 'Undated', score='8', posted_at=posted, assignment_id='u'),
            Grade('g6', 'c', 'Duplicate', score='8', posted_at=posted),
            Grade('g7', 'c', 'Other course', score='8', posted_at=posted),
        ])
        with patch.object(present, 'load_settings', return_value={}), patch.object(present, 'load_account', return_value={}):
            state = present._build_state(snapshot)
        rows = {row['id']: row for row in state['graded'] + state['pending']}
        for identifier in ('g1', 'g2', 'g3', 'p'):
            self.assertEqual(rows[identifier]['deadline_ts'], int(due.timestamp()))
            self.assertTrue(rows[identifier]['deadline'].startswith('Due '))
        for identifier in ('g4', 'g5', 'g6', 'g7'):
            self.assertEqual(rows[identifier]['deadline_ts'], 0)
            self.assertEqual(rows[identifier]['deadline'], 'Deadline unavailable')
        self.assertTrue(rows['g1']['due'].startswith('Posted '))
        self.assertEqual(rows['p']['due'], 'Posted date unavailable')
