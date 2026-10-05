import unittest
from unittest.mock import patch
import app.google_calendar as google


class GoogleSafety(unittest.TestCase):
    def test_deletion_requires_complete_nonempty_same_scope_manifest(self):
        for complete, events, scope, expected in [
            (False, [{'id':'new'}], 'a', []),
            (True, [], 'a', []),
            (True, [{'id':'new'}], 'b', []),
            (True, [{'id':'new'}], 'a', ['old']),
        ]:
            with self.subTest(complete=complete, events=events, scope=scope):
                account={'calendar_id':'test', 'sync_manifests':{'a':['old']}}
                with patch.object(google,'_ensure_access',side_effect=lambda a,t:a), patch.object(google,'_calendar_exists',return_value=True), patch.object(google,'_show_calendar'), patch.object(google,'_upsert_events',return_value=len(events)), patch.object(google,'_list_event_ids',return_value=['old','unrelated']), patch.object(google,'_delete_events') as delete, patch.object(google,'save_account'):
                    google.sync_account(account,events,complete=complete,scope=scope)
                    deleted = delete.call_args.args[2] if delete.called else []
                    self.assertEqual(deleted,expected)
