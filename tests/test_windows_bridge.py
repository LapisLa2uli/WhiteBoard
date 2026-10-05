import ctypes
import unittest
from unittest.mock import patch
from host import _windows as host


class BridgeABI(unittest.TestCase):
    def test_event_registration_writes_and_removes_token(self):
        calls = []

        @host.ADD_WEB_MESSAGE
        def add(web, handler, token):
            token[0] = 1234567890123
            return 0

        @host.REMOVE_WEB_MESSAGE
        def remove(web, token):
            calls.append(token)
            return 0

        with patch.object(host, '_vtable_slot', side_effect=lambda _, slot: ctypes.cast(add if slot in (34, 7) else remove, ctypes.c_void_p).value):
            host._hook_messages(100)
            host._unhook_messages(100)
        self.assertEqual(calls, [1234567890123, 1234567890123])

    def test_handler_supports_sdk_iid(self):
        handler = host._make_message_handler()
        wanted = host.GUID.from_text('{57213f19-00e6-49fa-8e07-898ea01ecbd2}')
        result = ctypes.c_void_p()
        self.assertEqual(host._query_interface(ctypes.addressof(handler), ctypes.pointer(wanted), ctypes.pointer(result)), 0)
        self.assertEqual(result.value, ctypes.addressof(handler))
