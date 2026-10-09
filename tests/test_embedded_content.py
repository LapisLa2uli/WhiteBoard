import unittest
from urllib.parse import parse_qs, urlparse
from blackboard import api
from blackboard.models import ContentNode

BASE='https://school.example'

class EmbeddedContentTests(unittest.TestCase):
    def test_document_contains_discoverable_files_and_links_to_parent_page(self):
        raw={'id':'_2_1','parentId':'_1_1','title':'Module example','contentHandler':{'id':'resource/x-bb-document'},
             'body':'<p>Read the handout and watch the clip.</p><a href="/bbcswebdav/xid-1_1">Handout.pdf</a><video><source src="/bbcswebdav/xid-2_1" type="video/mp4"></video>'}
        nodes=api.content_nodes_from_items([raw],'_9_1',BASE)
        self.assertEqual(nodes[0].kind,'folder')
        self.assertEqual(len(nodes),3)
        self.assertTrue(all(n.parent_id=='_2_1' for n in nodes[1:]))
        self.assertIn('Module example',nodes[1].display_name())
        self.assertIn('listContent.jsp',nodes[0].open_url)
        self.assertEqual(parse_qs(urlparse(nodes[0].open_url).query)['content_id'],['_1_1'])
        self.assertTrue(all('/bbcswebdav/' in n.download_path for n in nodes[1:]))

    def test_discussion_uses_forum_route_not_file_route(self):
        node=api._node_from_content_item({'id':'_2_1','title':'Discussion','contentHandler':{'id':'resource/x-bb-forumlink','discussionId':'_3_1'}},'_9_1',BASE)
        self.assertIn('/discussionboard/do/forum?',node.open_url)
        self.assertEqual(parse_qs(urlparse(node.open_url).query)['forum_id'],['_3_1'])

    def test_iframe_object_param_and_signed_urls(self):
        files=api.embedded_files_in_html('<iframe src="/bbcswebdav/xid-1_1?token=secret" title="Reading.pdf"></iframe><object><param name="movie" value="@X@embeddedfile.requestUrlStub@X@/bbcswebdav/xid-2_1"></object>')
        self.assertEqual(len(files),2)
        self.assertEqual(files[0][:3],('/bbcswebdav/xid-1_1','Reading.pdf','pdf'))
        self.assertEqual(files[1][0],'/bbcswebdav/xid-2_1')

    def test_catalog_corrects_earlier_fallback_without_replacing_download(self):
        nodes=[ContentNode('_2_1','_9_1',open_url=BASE+'/wrong'),ContentNode('_3_1','_9_1',open_url=BASE+'/file',download_path='/file')]
        entries=[api.ContentEntry('_9_1',n.id,'Example',url=BASE+'/correct') for n in nodes]
        api._apply_open_urls_from_catalog(nodes,entries)
        self.assertEqual(nodes[0].open_url,BASE+'/correct')
        self.assertEqual(nodes[1].open_url,BASE+'/file')

    def test_grouped_document_still_discovers_separate_attachments(self):
        node=ContentNode('_2_1','_9_1',kind='folder',handler='resource/x-bb-document')
        self.assertEqual(api._attachment_candidates([node]),[node])
        nodes=[node]
        api._apply_fetched_attachments(nodes,{'_2_1':[{'id':'_8_1','fileName':'extra.pdf'}]},'_9_1',BASE)
        self.assertEqual(node.kind,'folder')
        self.assertEqual(nodes[1].parent_id,node.id)

    def test_assignment_keeps_submission_link_and_separate_attachment(self):
        raw={'id':'_2_1','parentId':'_1_1','title':'Upload essay.docx','contentHandler':{'id':'resource/x-bb-assignment'}}
        node=api._node_from_content_item(raw,'_9_1',BASE)
        self.assertEqual(node.kind,'assignment')
        self.assertIn('/assignment/uploadAssignment',node.open_url)
        nodes=[node]
        api._apply_fetched_attachments(nodes,{'_2_1':[{'id':'_3_1','fileName':'rubric.pdf'}]},'_9_1',BASE)
        self.assertEqual(node.kind,'assignment')
        self.assertFalse(node.download_path)
        self.assertEqual(nodes[1].kind,'file')
        self.assertEqual(nodes[1].parent_id,'_1_1')

    def test_folder_download_skips_assignment_links(self):
        from server import _descendant_nodes
        folder=ContentNode('_1_1','_9_1',kind='folder')
        work=ContentNode('_2_1','_9_1',parent_id=folder.id,kind='assignment')
        file=ContentNode('_3_1','_9_1',parent_id=folder.id,kind='file')
        self.assertEqual(_descendant_nodes(folder,[folder,work,file]),[file])
