import unittest
from unittest.mock import patch, Mock
import server


class BrowserOpenTests(unittest.TestCase):
    def test_missing_external_browser_falls_back(self):
        start, builtin = Mock(side_effect=OSError('missing')), Mock()
        result=server._dispatch_open('chrome','https://school.example/work','Work',start=start,builtin=builtin)
        self.assertTrue(result['fallback'])
        builtin.assert_called_once()

    def test_mac_uses_open_without_winreg(self):
        with patch.object(server.sys,'platform','darwin'), patch('subprocess.run',return_value=Mock(returncode=0)) as run:
            self.assertTrue(server._start_browser('chrome','https://school.example'))
            self.assertEqual(run.call_args.args[0][:3], ['/usr/bin/open','-a','Google Chrome'])
