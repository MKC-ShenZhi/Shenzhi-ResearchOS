import unittest

from app.services.paper_resource.filename import build_pdf_filename


class PaperPdfFilenameTests(unittest.TestCase):
    def test_portable_filename_and_extension(self):
        cases = {
            ' 中文论文: A/B\\C?*<>|" ': '中文论文_ A_B_C______.pdf',
            'Title.PDF.pdf': 'Title.pdf',
            'Title.  ': 'Title.pdf',
            'A\r\nB\x00': 'A__B_.pdf',
            'CON': '_CON.pdf',
            'nul.txt': '_nul.txt.pdf',
            ' .pdf ': 'paper_test_123.pdf',
            '  ': 'paper_test_123.pdf',
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(build_pdf_filename(title, 'paper:test:123'), expected)

    def test_limits_utf8_bytes_without_breaking_unicode(self):
        filename = build_pdf_filename('论文' * 200, 'id')
        self.assertLessEqual(len(filename.encode('utf-8')), 184)
        self.assertNotIn('\ufffd', filename)
        self.assertTrue(filename.endswith('.pdf'))

    def test_empty_title_and_id_fall_back(self):
        self.assertEqual(build_pdf_filename('', ''), 'paper.pdf')
