import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import accounts
import crawl
import data
import present
from blackboard.models import Grade
from blackboard.store import Store
from persistence import read_json, write_json
from test_incremental import Session, item, run


class LoginCacheTests(unittest.TestCase):
    def setUp(self):
        self.old_root, self.old_key = data.APP_DIR, data.DATA_DIR.name
        self.temp = tempfile.TemporaryDirectory()
        data.APP_DIR = Path(self.temp.name)
        self.cookies = patch('host.clear_cookies').start()
        self.job = patch.dict(crawl.progress, busy=False)
        self.job.start()
        accounts.activate('https://school.example', {'id': '_5_1'}, 'student')

    def tearDown(self):
        self.job.stop()
        patch.stopall()
        present.publish_stage(None)
        data.APP_DIR = self.old_root
        data.use_profile(self.old_key)
        self.temp.cleanup()

    def seed(self):
        session = Session([item(1), item(2)])
        snapshot = run(session)
        snapshot.grades = [Grade('g', '_10_1', 'Private grade', score='99')]
        snapshot.user_name = 'Private student name'
        store = Store()
        store.snapshot = snapshot
        store.save_cache()
        return session, snapshot, data.SNAPSHOT_PATH.with_name('crawl-cache.json')

    def reenter(self):
        accounts.restore()  # Simulate restart before identity verification.
        self.assertFalse(present.build_state()['has_snapshot'])
        self.assertFalse(Store().load_cache())
        accounts.activate('https://school.example', {'id': '_5_1'}, 'student')
        previous = Store()
        self.assertFalse(previous.load_cache())
        self.assertTrue(previous.load_crawl_cache('https://school.example', '_5_1'))
        self.assertFalse(present.build_state()['has_snapshot'])
        return previous.snapshot

    def test_logout_restart_and_login_reuses_unchanged_files(self):
        session, first, path = self.seed()
        accounts.logout()
        self.cookies.assert_called_once()
        self.assertTrue(path.exists())
        payload, _ = read_json(path)
        self.assertEqual(payload['snapshot']['grades'], [])
        self.assertEqual(payload['snapshot']['user_name'], '')
        previous = self.reenter()
        session.calls.clear()
        result = run(session, previous)
        self.assertEqual(result.content_cache['stats']['reused'], 2)
        self.assertEqual(result.content_cache['stats']['fetched'], 0)
        self.assertEqual(len(session.calls), 1)
        self.assertIn('fields=', session.calls[0])
        self.assertEqual(result.content_nodes, first.content_nodes)

    def test_changes_after_login_fetch_only_changed_items_and_confirm_removal(self):
        session, first, path = self.seed()
        accounts.logout()
        previous = self.reenter()
        session.items = [session.items[0], item(3)]
        session.items[0].update(title='Edited', modified='2026-10-09T00:00:00Z')
        result = run(session, previous)
        self.assertEqual(result.content_cache['stats']['fetched'], 2)
        self.assertEqual(result.content_cache['stats']['pending_removal'], 1)
        store = Store()
        store.snapshot = result
        store.save_cache()
        accounts.logout()
        result = run(session, self.reenter())
        self.assertEqual(result.content_cache['stats']['removed'], 1)
        self.assertEqual(result.content_cache['stats']['reused'], 2)

    def test_sign_in_worker_passes_retained_index_after_authentication(self):
        session, snapshot, path = self.seed()
        accounts.logout()
        web = MagicMock(base_url=session.base_url, user={'id': '_5_1'}, metrics={})
        def fetch(_session, **kwargs):
            web.login.assert_called_once_with('student', 'test-password')
            self.assertEqual(data.DATA_DIR.name, accounts.profile_key(session.base_url, '_5_1'))
            self.assertEqual(kwargs['previous'].content_cache, snapshot.content_cache)
            return snapshot
        with patch.object(crawl, 'WebSession', return_value=web), \
                patch.object(crawl, 'fetch_snapshot', side_effect=fetch), \
                patch.object(crawl, '_sync_google'), patch.object(crawl, '_save_session'):
            crawl.start_login('student', 'test-password', session.base_url)
            self.assertTrue(crawl._done.wait(5))
            self.assertEqual(crawl.progress['error'], '')
            self.assertEqual(crawl.progress['stage'], 'complete')

    def test_other_school_or_account_cannot_load_retained_cache(self):
        self.seed()
        accounts.logout()
        accounts.activate('https://school.example', {'id': 'other'}, 'other')
        self.assertFalse(Store().load_crawl_cache('https://school.example', 'other'))
        accounts.activate('https://school.example', {'id': '_5_1'}, 'student')
        self.assertFalse(Store().load_crawl_cache('https://school.example', 'other'))
        self.assertFalse(Store().load_crawl_cache('https://other.example', '_5_1'))

    def test_opt_out_removes_retained_copy_and_backup(self):
        session, first, path = self.seed()
        store = Store()
        store.snapshot = first
        store.save_crawl_cache()
        store.save_crawl_cache()
        self.assertTrue(path.with_suffix('.json.bak').exists())
        accounts.logout(keep_crawl_cache=False)
        self.assertFalse(path.exists())
        self.assertFalse(path.with_suffix('.json.bak').exists())
        accounts.activate('https://school.example', {'id': '_5_1'}, 'student')
        self.assertFalse(Store().load_crawl_cache('https://school.example', '_5_1'))

    def test_corrupt_or_mismatched_cache_is_ignored(self):
        session, first, path = self.seed()
        accounts.logout()
        accounts.activate('https://school.example', {'id': '_5_1'}, 'student')
        path.write_text('{broken')
        self.assertFalse(Store().load_crawl_cache('https://school.example', '_5_1'))
        write_json(path, {'version': 1, 'origin': session.base_url, 'user_id': '_5_1',
                          'snapshot': {'user_id': 'someone else'}}, backup=False)
        self.assertFalse(Store().load_crawl_cache('https://school.example', '_5_1'))
