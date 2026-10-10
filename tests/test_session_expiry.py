import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import accounts
import crawl
import data
import server
from blackboard.auth import AuthExpiredError, SessionError
from session import WebSession


class SessionExpiryTests(unittest.TestCase):
    def test_identity_expiry_is_distinct_from_network_failure(self):
        for row in ({'status': 401}, {'status': 403},
                    {'status': 200, 'text': '<form id="loginForm">'},
                    {'status': 200, 'final_url': 'https://school.example/webapps/login/'}):
            session = WebSession('https://school.example')
            with patch.object(session, '_fetch_batch', return_value=[row]):
                with self.assertRaises(AuthExpiredError):
                    session.require_authenticated()
            with self.assertRaises(AuthExpiredError):
                session._check_cancelled()
        for status in (0, 429, 500, 503):
            session = WebSession('https://school.example')
            with patch.object(session, '_fetch_batch', return_value=[{'status': status}]):
                with self.assertRaises(SessionError) as error:
                    session.require_authenticated()
                self.assertNotIsInstance(error.exception, AuthExpiredError)
            self.assertFalse(session.auth_expired)

    def test_course_denial_does_not_expire_valid_identity(self):
        session = WebSession('https://school.example')
        session.logged_in = True
        url = 'https://school.example/course'
        with patch.object(session, '_fetch_batch', side_effect=[
            [{'url': url, 'status': 401}],
            [{'status': 200, 'text': '{"id":"student"}'}],
        ]):
            self.assertEqual(session._fetch([url])[0]['status'], 401)
            self.assertFalse(session.auth_expired)

    def test_expired_refresh_persists_login_requirement(self):
        session = MagicMock()
        session.require_authenticated.side_effect = AuthExpiredError('Session expired')
        with patch.dict(crawl.progress, busy=False), patch.object(crawl, 'WebSession', return_value=session), \
                patch.object(accounts, 'require_login') as require, patch.object(crawl, 'fetch_snapshot') as fetch:
            crawl._launch('refresh', 'student', '', 'https://school.example')
            self.assertTrue(crawl._done.wait(5))
            require.assert_called_once()
            fetch.assert_not_called()
            self.assertTrue(crawl.progress['auth_required'])

    def test_new_verified_login_clears_persisted_requirement(self):
        old_root, old_key = data.APP_DIR, data.DATA_DIR.name
        try:
            with tempfile.TemporaryDirectory() as directory:
                data.APP_DIR = Path(directory)
                accounts.activate('https://school.example', {'id': 'student'}, 'student')
                accounts.require_login()
                accounts.restore()
                self.assertTrue(accounts.auth_required())
                accounts.activate('https://school.example', {'id': 'student'}, 'student')
                self.assertFalse(accounts.auth_required())
        finally:
            data.APP_DIR = old_root
            data.use_profile(old_key)

    def test_background_check_skips_offline(self):
        with patch.object(accounts, 'auth_required', return_value=False), \
                patch.object(accounts, 'is_offline', return_value=True), patch('session.WebSession') as session:
            self.assertFalse(server._session_status()['auth_required'])
            session.assert_not_called()

    def test_logout_resets_old_job_and_partial_stage(self):
        import present
        from blackboard.models import Snapshot, Course
        old_root, old_key = data.APP_DIR, data.DATA_DIR.name
        try:
            with tempfile.TemporaryDirectory() as directory, patch('host.clear_cookies'), \
                    patch.dict(crawl.progress, busy=False, error='Session expired', auth_required=True, revision=3):
                data.APP_DIR = Path(directory)
                accounts.activate('https://school.example', {'id': 'student'}, 'student')
                present.publish_stage(Snapshot(courses=[Course('c', 'Old partial')]))
                accounts.logout()
                self.assertEqual(crawl.progress['error'], '')
                self.assertFalse(crawl.progress['auth_required'])
                self.assertEqual(crawl.progress['revision'], 0)
                self.assertIsNone(present._live_snapshot)
                self.assertFalse(present.build_state()['has_snapshot'])
        finally:
            data.APP_DIR = old_root
            data.use_profile(old_key)
            present.publish_stage(None)

    def test_background_check_skips_active_refresh(self):
        with patch.object(accounts, 'auth_required', return_value=False), \
                patch.object(accounts, 'is_offline', return_value=False), \
                patch.object(data, 'DATA_DIR', Path('profile')), patch.dict(crawl.progress, busy=True), \
                patch('session.WebSession') as session:
            self.assertTrue(server._session_status()['skipped'])
            session.assert_not_called()
