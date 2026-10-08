import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from blackboard.api import _apply_attachment, _attachment_child, _node_from_content_item
from blackboard.file_sizes import metadata_size, size_from_headers, enrich_file_sizes
from blackboard.models import ContentNode, Snapshot
from present import format_size
from session import WebSession

BASE = 'https://school.example'
NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


def headers(status=200, mime='application/pdf', **kw):
    return {'status': status, 'final_url': BASE+'/file.pdf',
            'headers': {'content-type': mime, **kw}}


class FileSizeTests(unittest.TestCase):
    def test_headers_use_total_range_not_one_byte_length(self):
        self.assertEqual(size_from_headers(headers(206, **{'content-range': 'bytes 0-0/3328388', 'content-length': '1'}), BASE), 3328388)
        self.assertEqual(size_from_headers(headers(**{'content-length': '1024'}), BASE), 1024)
        self.assertEqual(size_from_headers(headers(**{'content-length': '0'}), BASE), 0)
        self.assertEqual(size_from_headers(headers(416, **{'content-range': 'bytes */0'}), BASE), 0)

    def test_invalid_missing_compressed_and_error_lengths_remain_unknown(self):
        for row in (
            headers(), headers(**{'content-length': '-1'}), headers(**{'content-length': '1.5'}),
            headers(**{'content-length': '120', 'content-encoding': 'gzip'}),
            headers(302, **{'content-length': '120'}), headers(403, **{'content-length': '120'}),
            headers(200, mime='text/html', **{'content-length': '120'}),
            headers(200, mime='application/json', **{'content-length': '120'}),
            headers(206, **{'content-length': '1'}),
            headers(206, **{'content-range': 'bytes 0-0/*'}),
            headers(206, **{'content-range': 'bytes 0-1/1'}),
        ):
            self.assertIsNone(size_from_headers(row, BASE), row)

    def test_redirects_to_login_or_another_origin_are_rejected(self):
        for url in ('https://other.example/file.pdf', 'http://school.example/file.pdf', BASE+'/webapps/login/', BASE+'/auth/signin'):
            row=headers(**{'content-length': '123'})
            row['final_url']=url
            self.assertIsNone(size_from_headers(row, BASE))

    def test_html_attachment_range_is_a_file_but_html_login_is_not(self):
        row = headers(206, mime='text/html', **{'content-range':'bytes 0-0/1234'})
        row['url'] = BASE+'/learn/api/public/v1/courses/_1_1/contents/_2_1/attachments/_3_1/download'
        self.assertEqual(size_from_headers(row, BASE), 1234)
        row['status'] = 200
        row['headers']['content-length'] = '1234'
        self.assertIsNone(size_from_headers(row, BASE))
        row['status'] = 206
        row['final_url'] = BASE+'/webapps/login/'
        self.assertIsNone(size_from_headers(row, BASE))

    def test_api_sizes_distinguish_zero_and_invalid_metadata(self):
        self.assertEqual(metadata_size({'size': 0, 'fileSize': 12}), 0)
        self.assertEqual(metadata_size({}, {'fileSize': '512'}), 512)
        for value in (None, '', -1, 'bad', True, 1.5, '2.5'):
            self.assertIsNone(metadata_size({'size': value}))
        node = _node_from_content_item({'id': '_1_1', 'title': 'empty.txt', 'size': 0}, '_2_1', BASE)
        self.assertTrue(node.size_known)
        self.assertEqual(node.size_bytes, 0)
        node.size_bytes = 999
        _apply_attachment(node, {'id':'_3_1', 'fileName':'empty.txt', 'size':0}, node.course_id, BASE)
        self.assertTrue(node.size_known)
        self.assertEqual(node.size_bytes, 0)
        child = _attachment_child(node, {'id':'_4_1', 'fileName':'empty.txt', 'fileSize':0}, node.course_id, BASE)
        self.assertTrue(child.size_known)

    def test_zero_and_unknown_survive_persistence(self):
        for known, expected in ((True, '0 B'), (False, '—')):
            node=ContentNode('_1_1', '_2_1', size_bytes=0, size_known=known, size_checked_at=NOW)
            saved=ContentNode.from_dict(node.to_dict())
            self.assertEqual(saved.size_known, known)
            self.assertEqual(saved.size_checked_at, NOW)
            self.assertEqual(format_size(saved.size_bytes if saved.size_known else None), expected)
        self.assertEqual(format_size(3328388), '3.2 MB')
        self.assertFalse(ContentNode.from_dict({'id':'old', 'size_bytes':0}).size_known)
        self.assertTrue(ContentNode.from_dict({'id':'old', 'size_bytes':123}).size_known)

    def test_enrichment_deduplicates_and_caches_known_and_failed_sizes(self):
        class Metadata:
            calls=[]
            def _tell(self, *args): pass
            def get_file_metadata_many(self, paths):
                self.calls.append(paths)
                return {'/empty':0, '/file':2048, '/unknown':None}
        s=Metadata()
        nodes=[ContentNode(str(i),'c',download_path=p) for i,p in enumerate(['/empty','/file','/file','/unknown'])]
        enrich_file_sizes(s,nodes,now=NOW)
        self.assertEqual(s.calls,[['/empty','/file','/unknown']])
        self.assertTrue(nodes[0].size_known)
        self.assertEqual(nodes[2].size_bytes,2048)
        restored=[ContentNode.from_dict(n.to_dict()) for n in nodes]
        enrich_file_sizes(s,restored,now=NOW+timedelta(hours=1))
        self.assertEqual(len(s.calls),1)
        enrich_file_sizes(s,restored,now=NOW+timedelta(days=1))
        self.assertEqual(s.calls[-1],['/unknown'])

    def test_session_restricts_origins_and_does_not_fetch_duplicate_urls(self):
        s=WebSession(BASE)
        s._tell=lambda *args: None
        def batch(script,key):
            self.assertIn('mode:"same-origin"',script)
            self.assertIn('await res.body.cancel()',script)
            self.assertNotIn('res.text()',script)
            self.assertNotIn('res.arrayBuffer()',script)
            self.assertNotIn('https://other.example',script)
            return [dict(headers(206, **{'content-range':'bytes 0-0/2048'}), url=BASE+'/file', requests=1)]
        with patch.object(s,'_run_batch_script',side_effect=batch) as invoke:
            result=s.get_file_metadata_many(['/file','/file',BASE+'/file','https://other.example/file'])
        self.assertEqual(invoke.call_count,1)
        self.assertEqual(result['/file'],2048)
        self.assertNotIn('https://other.example/file',result)
        self.assertEqual(s.metrics['metadata_requests'],1)

    def test_incremental_refresh_preserves_sizes_without_new_metadata_requests(self):
        from test_incremental import Session, item, run
        class WithSizes(Session):
            size_calls=0
            def get_file_metadata_many(self, paths):
                self.size_calls += 1
                return dict.fromkeys(paths, 3210)
        s=WithSizes([item(1)])
        first=run(s)
        self.assertEqual(first.content_nodes[0].size_bytes,3210)
        second=run(s,Snapshot.from_dict(first.to_dict()))
        self.assertEqual(s.size_calls,1)
        self.assertTrue(second.content_nodes[0].size_known)
        self.assertEqual(second.content_nodes[0].size_bytes,3210)
        run(s,second,full=True)
        self.assertEqual(s.size_calls,2)
