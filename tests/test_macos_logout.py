"""Platform-independent callback contract test; native WKWebView still needs a Mac."""
import ast
from pathlib import Path
import threading
import unittest
from unittest.mock import MagicMock, patch


class MacLogoutTests(unittest.TestCase):
    def test_logout_waits_for_all_website_data_to_be_removed(self):
        tree = ast.parse(Path('host/_macos.py').read_text(encoding='utf-8'))
        fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'clear_cookies')
        store = MagicMock()
        called = threading.Event()
        def remove(types, since, callback):
            called.set()
            threading.Timer(.04, callback).start()
        store.removeDataOfTypes_modifiedSince_completionHandler_.side_effect = remove
        values = {'threading': threading, '_on_main': lambda call: call(), '_docs': {'tabs': [{'id': 'one'}]},
                  '_close_tab': MagicMock(), '_state': {'store': store}, 'WebKit': MagicMock(), 'Foundation': MagicMock()}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<mac-logout>', 'exec'), values)
        with patch('secure_storage.delete_secret') as delete:
            values['clear_cookies']()
            delete.assert_called_once()
        self.assertTrue(called.is_set())
        values['_close_tab'].assert_called_once_with('one')

