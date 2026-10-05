import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import accounts
import data
from blackboard.store import load_settings, save_settings


class AccountTests(unittest.TestCase):
    def test_origin_validation(self):
        self.assertEqual(accounts.school_origin('https://School.example:443/'), 'https://school.example')
        for value in ('http://school.example', 'https://user:pass@school.example', 'https://school.example/login'):
            with self.assertRaises(ValueError):
                accounts.school_origin(value)

    def test_profiles_do_not_share_marks_or_school_identity(self):
        old_root, old_key = data.APP_DIR, data.DATA_DIR.name
        try:
            with tempfile.TemporaryDirectory() as directory:
                data.APP_DIR = Path(directory)
                a = accounts.activate('https://one.example', {'id': '1'}, 'first')
                settings = load_settings()
                settings['marked_submitted_assignments'] = ['a']
                save_settings(settings)
                b = accounts.activate('https://one.example', {'id': '2'}, 'second')
                self.assertNotEqual(a, b)
                self.assertEqual(load_settings()['marked_submitted_assignments'], [])
                self.assertNotEqual(a, accounts.profile_key('https://two.example', '1'))
                accounts.activate('https://one.example', {'id': '1'}, 'first')
                self.assertEqual(load_settings()['marked_submitted_assignments'], ['a'])
        finally:
            data.APP_DIR = old_root
            data.use_profile(old_key)

    def test_existing_session_does_not_accept_different_username(self):
        from session import WebSession
        session = WebSession('https://school.example')
        session.user = {'id': '1', 'userName': 'first'}
        with patch('host.clear_cookies') as clear:
            with self.assertRaises(RuntimeError):
                session._verify_user('second')
            clear.assert_called_once()
