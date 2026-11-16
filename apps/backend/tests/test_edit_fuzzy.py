"""edit_file 与 pi edit-diff.ts 对齐的回归测试（模糊归一、重叠/空/无变更拒绝）。"""
import tempfile
import unittest
from pathlib import Path

from app.core.errors import BusinessError
from app.services.agent.workspace import Workspace


class EditFuzzyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    async def test_fuzzy_smart_quotes_dashes_spaces(self):
        (self.ws.root / 'f.md').write_text(
            '含\u201c智能引号\u201d和长破折号\u2014与\u00a0nbsp、尾部空白  \n',
            encoding='utf-8')
        for old, new in (('含\u201c智能引号\u201d', '含A引号'),
                         ('长破折号\u2014与', '长破折号-与'),
                         ('nbsp、尾部空白', 'nbsp、无空白')):
            await self.ws.edit('f.md', [{'old_text': old, 'new_text': new}])
        out = (self.ws.root / 'f.md').read_text(encoding='utf-8')
        self.assertIn('含A引号', out)
        self.assertIn('长破折号-与', out)
        self.assertIn('无空白', out)

    async def test_edit_rejects_empty_overlap_nochange(self):
        (self.ws.root / 'f.md').write_text('aaa bbb ccc\n', encoding='utf-8')
        with self.assertRaises(BusinessError):
            await self.ws.edit('f.md', [{'old_text': '', 'new_text': 'x'}])
        with self.assertRaises(BusinessError):
            await self.ws.edit('f.md', [{'old_text': 'aaa bbb', 'new_text': 'x'},
                                        {'old_text': 'bbb ccc', 'new_text': 'y'}])
        with self.assertRaises(BusinessError):
            await self.ws.edit('f.md', [{'old_text': '不存在', 'new_text': 'x'}])

    async def test_edit_preserves_bom_and_crlf(self):
        (self.ws.root / 'f.md').write_bytes('\ufeffa\r\nb\r\n'.encode())
        await self.ws.edit('f.md', [{'old_text': 'b', 'new_text': 'c'}])
        raw = (self.ws.root / 'f.md').read_bytes()
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        self.assertIn(b'\r\n', raw)

    async def test_fuzzy_keeps_unchanged_lines_original_bytes(self):
        (self.ws.root / 'f.md').write_text('第一行  \n第二行\u201c引号\u201d\n', encoding='utf-8')
        await self.ws.edit('f.md', [{'old_text': '第二行\u201c引号\u201d', 'new_text': '改'}])
        out = (self.ws.root / 'f.md').read_text(encoding='utf-8')
        self.assertEqual(out, '第一行  \n改\n')