import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from blackboard.models import ContentNode
import server


class DownloadTests(unittest.TestCase):
    def test_filename_exhaustion_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for i in range(1,110):
                (root/('file.pdf' if i==1 else f'file ({i}).pdf')).write_bytes(b'original')
            first=server._reserve_path(root/'file.pdf')
            second=server._reserve_path(root/'file.pdf')
            self.assertNotEqual(first,second)
            self.assertEqual((root/'file.pdf').read_bytes(),b'original')

    def test_zip_streams_each_file_and_cleans_up_failures(self):
        folder=ContentNode(id='f',course_id='c',title='Folder',kind='folder')
        nodes=[ContentNode(id='1',course_id='c',parent_id='f',title='one.bin',download_path='/one')]
        class Session:
            def _check_cancelled(self): pass
            def download_to(self,path,output):
                for _ in range(20): output.write(b'x'*65536)
        with tempfile.TemporaryDirectory() as directory, patch.object(server,'_zip_progress'):
            root=Path(directory)
            name=server._write_folder_zip(Session(),root,folder,nodes,{'f':folder},[])
            with zipfile.ZipFile(root/name) as archive:
                self.assertEqual(archive.getinfo('one.bin').file_size,20*65536)
            with patch.object(Session,'download_to',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    server._write_folder_zip(Session(),root,folder,nodes,{'f':folder},[])
            self.assertEqual([p.name for p in root.iterdir()],[name])
