import unittest
from unittest.mock import patch
from blackboard.models import Snapshot, Course
import present


class StagedLoadingTests(unittest.TestCase):
    def test_live_stage_is_a_copy_and_cancellation_restores_disk_view(self):
        snapshot=Snapshot(courses=[Course(id='a',name='One')])
        present.publish_stage(snapshot)
        snapshot.courses.clear()
        self.assertEqual(len(present.load_snapshot().courses),1)
        present.publish_stage(None)
        self.assertIsNone(present._live_snapshot)

    def test_google_status_does_not_build_dashboard(self):
        import server
        with patch.object(server,'build_state',side_effect=AssertionError('expensive state')), patch.object(server,'load_account',return_value={}):
            self.assertIn('google',server.handle('/api/google/status'))
