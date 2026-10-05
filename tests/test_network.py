import unittest
from unittest.mock import patch
from session import WebSession


class NetworkTests(unittest.TestCase):
    def test_successful_duplicate_requests_share_one_fetch(self):
        session = WebSession('https://school.example')
        with patch.object(session,'_fetch_batch',return_value=[{'url':'https://school.example/a','status':200,'text':'{}'}]) as fetch:
            first=session._fetch(['https://school.example/a']*2)
            second=session._fetch(['https://school.example/a'])
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(first[0],second[0])

    def test_invalid_json_is_an_explicit_failure(self):
        session = WebSession('https://school.example')
        with patch.object(session,'_fetch',return_value=[{'url':'/a','status':200,'text':'{"truncated":'}]):
            row=session.get_json_many(['/a'])[0]
            self.assertEqual(row['status'],0)
            self.assertTrue(row['error'])
            self.assertTrue(session.request_warnings)
