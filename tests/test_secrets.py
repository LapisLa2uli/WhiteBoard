import tempfile
import unittest
from pathlib import Path
from secure_storage import save_secret, load_secret, delete_secret


class SecretTests(unittest.TestCase):
    def test_os_encryption_and_plaintext_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tokens.json'
            path.write_text('{"refresh_token":"test-private-value"}')
            self.assertEqual(load_secret(path)['refresh_token'], 'test-private-value')
            self.assertNotIn(b'test-private-value', path.read_bytes())
            save_secret(path, {'refresh_token': 'replacement'})
            self.assertEqual(load_secret(path), {'refresh_token': 'replacement'})
            delete_secret(path)
            self.assertFalse(path.exists())
