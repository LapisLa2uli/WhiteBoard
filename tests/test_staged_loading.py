import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from blackboard.models import Snapshot, Course
import present


class StagedLoadingTests(unittest.TestCase):
    def test_checkpoint_survives_restart_without_replacing_complete_cache(self):
        import data
        import blackboard.store as storage
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'snapshot.json'
            with patch.object(data, 'SNAPSHOT_PATH', path), patch.object(storage, 'SNAPSHOT_PATH', path), patch.object(storage, 'DATA_DIR', Path(folder)):
                store = storage.Store()
                store.snapshot = Snapshot(courses=[Course(id='a', name='Checkpoint')])
                store.save_dashboard()
                self.assertEqual(present.load_snapshot().courses[0].name, 'Checkpoint')
                self.assertIn('indexing', present.load_snapshot().errors)
                self.assertFalse(path.exists())
                store.snapshot.files_indexed = True
                store.save_cache()
                self.assertFalse(path.with_name('dashboard.json').exists())
                store.snapshot.courses[0].name = 'Incomplete refresh'
                store.save_dashboard()
                self.assertEqual(present.load_snapshot().courses[0].name, 'Checkpoint')

    def test_contents_are_not_complete_before_indexing(self):
        import server
        result = {'content_nodes': [], 'content_loaded': False, 'files_indexed': False, 'revision': 1}
        with patch.object(server, 'build_state', return_value=result), patch.dict(server.progress, busy=True):
            response = server.handle('/api/content')
            self.assertFalse(response['content_loaded'])
            self.assertTrue(response['content_indexing'])

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
