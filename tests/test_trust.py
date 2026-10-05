import unittest
import data
from host.trust import trusted_page


class TrustTests(unittest.TestCase):
    def test_only_packaged_pages_can_use_bridge(self):
        page = (data.resource_root() / 'static' / 'index.html').as_uri()
        self.assertTrue(trusted_page(page + '#/home'))
        for value in ('https://example.com/index.html', 'file:///tmp/index.html', page + '/other', 'file://remote/index.html'):
            self.assertFalse(trusted_page(value))
