import threading
import unittest
from unittest.mock import patch, MagicMock
import crawl


class JobsTests(unittest.TestCase):
    def tearDown(self):
        crawl.progress['busy'] = False
        crawl._cancel.clear()

    def test_only_one_worker_starts(self):
        crawl.progress['busy'] = False
        with patch.object(crawl.threading, 'Thread') as worker:
            crawl._launch('refresh', '', '', 'https://example.com')
            first = crawl.progress['id']
            crawl._launch('refresh', '', '', 'https://example.com')
            self.assertEqual(worker.call_count, 1)
            self.assertEqual(first, crawl.progress['id'])

    def test_cancelled_fetch_cannot_save_or_sync(self):
        crawl.progress['busy'] = False
        session = MagicMock()
        def fetch(*args, **kwargs):
            crawl._cancel.set()
            return MagicMock()
        with patch.object(crawl, 'WebSession', return_value=session), patch.object(crawl, 'fetch_snapshot', side_effect=fetch), patch.object(crawl, 'Store') as store, patch.object(crawl, '_sync_google') as sync:
            crawl._launch('refresh', '', '', 'https://example.com')
            self.assertTrue(crawl._done.wait(5))
            store.assert_not_called()
            sync.assert_not_called()
            self.assertTrue(crawl.progress['cancelled'])

    def test_stale_cancel_does_not_cancel_new_job(self):
        crawl.progress.update(busy=True, id='new')
        crawl.cancel_job('old')
        self.assertFalse(crawl._cancel.is_set())
