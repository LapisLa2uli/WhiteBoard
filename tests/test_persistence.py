import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from persistence import read_json, write_json, validate_snapshot


class PersistenceTests(unittest.TestCase):
    def test_interrupted_replace_preserves_previous_document(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            write_json(path, {'old': True})
            with patch('persistence.os.replace', side_effect=OSError('disk unavailable')):
                with self.assertRaises(OSError):
                    write_json(path, {'new': True}, backup=False)
            self.assertEqual(json.loads(path.read_text()), {'old': True})
            self.assertFalse(list(Path(directory).glob('*.tmp')))

    def test_truncated_or_invalid_snapshot_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            write_json(path, {'courses': []})
            write_json(path, {'courses': [{'id': 'one'}]})
            for bad in ('{"courses":', '{"courses":42}'):
                path.write_text(bad)
                value, message = read_json(path, validate=validate_snapshot)
                self.assertEqual(value, {'courses': []})
                self.assertIn('Recovered', message)
