import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock
import server


class BrowserOpenTests(unittest.TestCase):
    def test_snooze_persists_for_one_profile_and_browser_and_expires_at_30_minutes(self):
        from blackboard import store
        with TemporaryDirectory() as folder, patch.object(store, 'DATA_DIR', Path(folder)), \
                patch.object(store, 'SETTINGS_PATH', Path(folder) / 'first.json'), \
                patch.object(server.data, 'SETTINGS_PATH', store.SETTINGS_PATH), \
                patch.object(server, '_launch_target', return_value=('https://school.example/file', 'File')), \
                patch.object(server, '_start_browser', return_value=True) as start, \
                patch('host.open_document'), patch.object(server.time, 'time', return_value=10000) as clock:
            settings = dict(base_url='https://school.example', page_opener='chrome')
            store.save_settings(settings)
            request = dict(browser='chrome', browser_action='page', snooze_notice=True)
            # Opening sign-in, an ordinary open, and a built-in fallback never snooze.
            for change, opened in [({'browser_action':'signin'}, True), ({'snooze_notice':False}, True), ({}, False)]:
                start.return_value = opened
                server._open_page({**request, **change})
                self.assertTrue(server._open_page({})['browser_notice'])
            start.return_value = True
            self.assertEqual(server._open_page(request)['opened_with'], 'chrome')
            clock.return_value = 11799
            self.assertEqual(server._open_page({})['opened_with'], 'chrome')
            with patch.object(store, 'SETTINGS_PATH', Path(folder) / 'second.json'):
                store.save_settings(settings)
                self.assertTrue(server._open_page({})['browser_notice'])
            store.update_settings(lambda prefs: prefs.update(page_opener='edge'))
            self.assertTrue(server._open_page({})['browser_notice'])
            store.update_settings(lambda prefs: prefs.update(page_opener='chrome'))
            clock.return_value = 11800
            self.assertTrue(server._open_page({})['browser_notice'])

    def open_page(self, settings, target, body=None, opened=True):
        with patch.object(server, 'load_settings', return_value=settings), \
                patch.object(server, '_launch_target', return_value=(target, 'Essay')), \
                patch.object(server, '_start_browser', return_value=opened) as start, \
                patch('host.open_document') as builtin:
            result = server._open_page(body or {})
            return result, start.call_args_list, builtin.call_args_list

    def test_external_blackboard_link_requires_notice_before_opening(self):
        for browser in ('system', 'edge', 'chrome'):
            settings = dict(base_url='https://school.example', username='student', page_opener=browser)
            result, calls, builtin = self.open_page(settings, 'https://school.example/work')
            self.assertTrue(result['browser_notice'])
            self.assertEqual(result['username'], 'student')
            self.assertEqual(result['browser'], browser)
            self.assertEqual(calls, [])
            self.assertEqual(builtin, [])

    def test_signin_and_requested_page_open_in_the_same_browser(self):
        settings = dict(base_url='https://school.example', username='student', page_opener='chrome')
        result, calls, builtin = self.open_page(settings, 'https://school.example/work',
                                               dict(browser='chrome', browser_action='signin'))
        self.assertTrue(result['ok'])
        self.assertEqual(calls[0].args, ('chrome', 'https://school.example/webapps/login/'))
        self.assertEqual(builtin, [])
        result, calls, builtin = self.open_page(settings, 'https://school.example/work',
                                               dict(browser='chrome', browser_action='page'))
        self.assertEqual(calls[0].args, ('chrome', 'https://school.example/work'))
        self.assertEqual(result['opened_with'], 'chrome')

    def test_failed_external_signin_never_falls_back_to_integrated_login(self):
        settings = dict(base_url='https://school.example', page_opener='edge')
        result, calls, builtin = self.open_page(settings, 'https://school.example/work',
                                               dict(browser='edge', browser_action='signin'), opened=False)
        self.assertFalse(result['ok'])
        self.assertEqual(builtin, [])

    def test_changed_browser_requires_new_notice(self):
        settings = dict(base_url='https://school.example', page_opener='edge')
        result, calls, _ = self.open_page(settings, 'https://school.example/work',
                                        dict(browser='chrome', browser_action='page'))
        self.assertTrue(result['browser_notice'])
        self.assertEqual(calls, [])

    def test_builtin_and_other_sites_do_not_show_school_signin(self):
        settings = dict(base_url='https://school.example', page_opener='builtin')
        result, calls, builtin = self.open_page(settings, 'https://school.example/work')
        self.assertEqual(result['opened_with'], 'builtin')
        self.assertEqual(len(builtin), 1)
        settings['page_opener'] = 'system'
        for url in ('https://other.example/work', 'https://school.example.attacker.test/work'):
            result, calls, _ = self.open_page(settings, url)
            self.assertNotIn('browser_notice', result)
            self.assertEqual(calls[0].args, ('system', url))

    def test_missing_external_browser_falls_back(self):
        start, builtin = Mock(side_effect=OSError('missing')), Mock()
        result=server._dispatch_open('chrome','https://school.example/work','Work',start=start,builtin=builtin)
        self.assertTrue(result['fallback'])
        builtin.assert_called_once()

    def test_mac_uses_open_without_winreg(self):
        with patch.object(server.sys,'platform','darwin'), patch('subprocess.run',return_value=Mock(returncode=0)) as run:
            self.assertTrue(server._start_browser('chrome','https://school.example'))
            self.assertEqual(run.call_args.args[0][:3], ['/usr/bin/open','-a','Google Chrome'])
