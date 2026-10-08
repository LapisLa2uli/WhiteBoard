import copy
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs

from blackboard.models import Snapshot, Course, ContentNode
from blackboard.incremental import crawl, _listings

NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)
CID = '_10_1'


def item(i, **kw):
    return dict(id=f'_{i}_1', title=f'File {i}', modified='2026-10-01T00:00:00Z',
                created='2026-09-01T00:00:00Z', hasChildren=False,
                contentHandler={'id': 'resource/x-bb-file'}, **kw)


class Session:
    base_url = 'https://school.example'

    def __init__(self, items):
        self.items = copy.deepcopy(items)
        self.calls = []
        self.metrics = {}
        self.network_errors = []
        self.request_warnings = []
        self.fail = False
        self.recursive_forbidden = False
        self.forbidden_folder = ''
        self.cancelled = False
        self.attachments = {}

    def _tell(self, *args):
        self._check_cancelled()

    def _check_cancelled(self):
        if self.cancelled:
            raise RuntimeError('cancelled')

    def crawl_html_links(self, urls):
        self.calls.extend(urls)
        return []

    def get_json_many(self, paths):
        rows = []
        for path in paths:
            self.calls.append(path)
            url = urlparse(path)
            q = parse_qs(url.query)
            tail = url.path.split('/contents')[-1]
            status = 200
            if self.fail:
                data, status = None, 503
            elif not tail or tail.endswith('/children'):
                if ('recursive' in q and self.recursive_forbidden) or tail == f'/{self.forbidden_folder}/children':
                    data, status = None, 403
                else:
                    entries = self.items
                    if 'recursive' not in q:
                        parent = tail.split('/')[1] if tail else ''
                        entries = [x for x in entries if (x.get('parentId') or '') == parent]
                    if 'fields' in q:
                        fields = q['fields'][0].split(',')
                        entries = [{k: v for k, v in x.items() if k in fields} for x in entries]
                    data = {'results': copy.deepcopy(entries)}
            elif tail.endswith('/attachments'):
                iid = tail.split('/')[1]
                data = {'results': self.attachments.get(iid, [{'id': '_99_1', 'fileName': iid + '.pdf', 'mimeType': 'application/pdf'}])}
            else:
                data = next((copy.deepcopy(x) for x in self.items if x['id'] == tail.strip('/')), None)
                if data is None:
                    status = 404
            rows.append({'url': self.base_url + path, 'status': status, 'data': data})
        return rows


def run(session, previous=None, **kw):
    snapshot = Snapshot(user_id='_5_1', courses=[Course(CID, 'Course')])
    entries, snapshot.content_nodes = crawl(session, snapshot, snapshot.courses, previous=previous, now=kw.pop('now', NOW), **kw)
    return snapshot


class IncrementalTests(unittest.TestCase):
    def test_unchanged_reuses_enrichment_after_disk_roundtrip(self):
        session = Session([item(1), item(2)])
        session.attachments['_1_1'] = [{'id': '_91_1', 'fileName': 'a.pdf'}, {'id': '_92_1', 'fileName': 'b.pdf'}]
        first = run(session)
        before = first.to_dict()
        session.calls.clear()
        second = run(session, Snapshot.from_dict(before))
        self.assertEqual(before, first.to_dict())
        self.assertEqual(sorted((n.to_dict() for n in first.content_nodes), key=str), sorted((n.to_dict() for n in second.content_nodes), key=str))
        self.assertEqual(len(session.calls), 1)
        self.assertIn('fields=', session.calls[0])
        self.assertEqual(second.content_cache['stats']['reused'], 2)

    def test_add_edit_move_and_removal_confirmation(self):
        s = Session([item(1), item(2)])
        first = run(s)
        s.items[0].update(title='Edited', modified='2026-10-02T00:00:00Z', parentId='_8_1')
        s.items.append(item(3))
        s.items = [x for x in s.items if x['id'] != '_2_1']
        second = run(s, first)
        self.assertEqual(len(second.content_nodes), 3)
        self.assertEqual(next(n for n in second.content_nodes if n.id == '_1_1').parent_id, '_8_1')
        self.assertEqual(second.content_cache['stats']['fetched'], 2)
        third = run(s, second)
        self.assertEqual({n.id for n in third.content_nodes}, {'_1_1', '_3_1'})
        self.assertEqual(third.content_cache['stats']['removed'], 1)

    def test_parent_move_without_modified_change_is_fetched(self):
        s = Session([item(1)])
        first = run(s)
        s.items[0]['parentId'] = '_88_1'
        second = run(s, first)
        self.assertEqual(second.content_nodes[0].parent_id, '_88_1')
        self.assertEqual(second.content_cache['stats']['fetched'], 1)

    def test_incomplete_inventory_preserves_absence_and_retries(self):
        s = Session([item(1)])
        first = run(s)
        s.items = []
        second = run(s, first)
        s.fail = True
        failed = run(s, second)
        self.assertEqual(len(failed.content_nodes), 1)
        self.assertFalse(failed.completeness['files'])
        self.assertEqual(failed.content_cache['courses'][CID]['records']['_1_1']['missing'], 1)
        s.fail = False
        self.assertEqual(run(s, failed).content_nodes, [])

    def test_folder_fallback_and_forbidden_scope(self):
        folder = item(1)
        folder.update(hasChildren=True, contentHandler={'id': 'resource/x-bb-folder'})
        s = Session([folder, item(2, parentId='_1_1')])
        s.recursive_forbidden = True
        first = run(s)
        self.assertTrue(first.completeness['files'])
        s.forbidden_folder = '_1_1'
        second = run(s, first)
        third = run(s, second)
        self.assertEqual(len(third.content_nodes), 2)
        self.assertFalse(third.completeness['files'])

    def test_full_and_daily_revalidation(self):
        s = Session([item(1)])
        first = run(s)
        for kwargs in ({'full': True}, {'now': NOW + timedelta(days=1)}):
            s.calls.clear()
            refreshed = run(s, first, **kwargs)
            self.assertEqual(refreshed.content_cache['stats']['fetched'], 1)
            self.assertTrue(any('/attachments' in p for p in s.calls))
            self.assertNotIn('fields=', s.calls[0])

    def test_missing_or_invalid_revision_is_never_reused(self):
        for value in (None, '', 'invalid'):
            s = Session([item(1)])
            s.items[0]['modified'] = value
            first = run(s)
            self.assertEqual(run(s, first).content_cache['stats']['fetched'], 1)

    def test_user_and_school_isolation(self):
        s = Session([item(1)])
        first = run(s)
        for key, value in [('user_id', '_9_1'), ('origin', 'https://other.example')]:
            other = copy.deepcopy(first)
            other.content_cache[key] = value
            self.assertEqual(run(s, other).content_cache['stats']['reused'], 0)

    def test_cancelled_reconcile_does_not_mutate_previous(self):
        s = Session([item(1)])
        first = run(s)
        before = copy.deepcopy(first.to_dict())
        s.cancelled = True
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            run(s, first)
        self.assertEqual(first.to_dict(), before)

    def test_failed_attachment_refresh_preserves_old_files_and_retries(self):
        class Failing(Session):
            broken = False
            def get_json_many(self, paths):
                rows = super().get_json_many(paths)
                if self.broken:
                    for row in rows:
                        if '/attachments' in row['url']:
                            row.update(status=503, data=None)
                return rows
        s = Failing([item(1)])
        first = run(s)
        s.items[0]['modified'] = '2026-10-03T00:00:00Z'
        s.broken = True
        second = run(s, first)
        self.assertEqual(second.content_nodes[0].to_dict(), first.content_nodes[0].to_dict())
        self.assertFalse(second.completeness['files'])
        s.broken = False
        third = run(s, second)
        self.assertEqual(third.content_cache['stats']['fetched'], 1)
        self.assertTrue(third.completeness['files'])

    def test_older_snapshot_keeps_unverified_nodes_during_upgrade(self):
        s = Session([])
        old = Snapshot(user_id='_5_1', courses=[Course(CID, 'Course', blackboard_url=s.base_url+'/course')],
                       content_nodes=[ContentNode('_1_1', CID, filename='saved.pdf')])
        s.fail = True
        failed = run(s, old)
        self.assertEqual(len(failed.content_nodes), 1)
        s.fail = False
        first = run(s, failed)
        self.assertEqual(len(first.content_nodes), 1)
        self.assertEqual(run(s, first).content_nodes, [])

    def test_selected_course_change_keeps_other_course_cache(self):
        s = Session([item(1)])
        first = run(s)
        filtered = Snapshot(user_id=first.user_id)
        crawl(s, filtered, [], previous=first, now=NOW)
        self.assertIn(CID, filtered.content_cache['courses'])
        self.assertEqual(run(s, filtered).content_cache['stats']['reused'], 1)

    def test_full_refresh_route_passes_explicit_flag(self):
        from unittest.mock import patch
        import server
        with patch.object(server, 'start_refresh', return_value={}) as refresh:
            server.handle('/api/refresh', {'full': True})
            refresh.assert_called_once_with(full=True)

    def test_newly_visible_old_item_is_discovered(self):
        s = Session([item(1)])
        first = run(s)
        s.items.append(item(2))
        second = run(s, first)
        self.assertEqual(second.content_cache['stats']['fetched'], 1)
        self.assertEqual(second.content_cache['stats']['reused'], 1)

    def test_pagination_failure_cycle_duplicates_and_foreign_url_are_incomplete(self):
        class Pages(Session):
            def get_json_many(self, paths):
                return [{'url': self.base_url + p, **self.responses[p]} for p in paths]
        s = Pages([])
        a = {'id': '_1_1'}
        b = {'id': '_2_1'}
        for last in ({'status': 503, 'data': None},
                     {'status': 200, 'data': {'results': [a]}},
                     {'status': 200, 'data': {'results': [b], 'paging': {'nextPage': '/first'}}},
                     {'status': 200, 'data': {'results': [b], 'paging': {'nextPage': 'https://other.example/page'}}}):
            s.responses = {'/first': {'status': 200, 'data': {'results': [a], 'paging': {'nextPage': '/last'}}}, '/last': last}
            self.assertFalse(_listings(s, {'course': '/first'})['course']['complete'])
        s.responses['/last'] = {'status': 200, 'data': {'results': [b]}}
        result = _listings(s, {'course': '/first'})['course']
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['items']), 2)
