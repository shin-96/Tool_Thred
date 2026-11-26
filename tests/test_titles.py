import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from threadstudio.store import Store
from threadstudio.titles import slugify_title, summarize_title


class TitleTests(unittest.TestCase):
    def test_summary_drops_ui_junk_lines(self):
        text = 'Tôi rời khỏi chiếc giường ấm áp và lao ra ngoài\nTop\nView activity'
        self.assertEqual(summarize_title(text), 'Tôi rời khỏi chiếc giường ấm áp và lao ra ngoài')

    def test_summary_truncates_at_word_boundary(self):
        out = summarize_title('một hai ba bốn năm sáu bảy tám chín mười ' * 5, limit=30)
        self.assertLessEqual(len(out), 31)
        self.assertTrue(out.endswith('…'))

    def test_slugify_strips_vietnamese_diacritics(self):
        self.assertEqual(slugify_title('Đàn ông có sự nghiệp thích phụ nữ trẻ?'),
                         'dan-ong-co-su-nghiep-thich-phu-nu-tre')


class DeleteVideoTests(unittest.TestCase):
    def test_delete_removes_video_and_its_uploads(self):
        with tempfile.TemporaryDirectory() as td:
            store = Store(Path(td) / 'db.sqlite')
            vid = store.add_video(str(Path(td) / 'v.mp4'), 'Video test', {})
            store.new_upload(vid, 'browser:main', 'browser', 'cap')
            row = store.delete_video(vid)
            self.assertEqual(row['title'], 'Video test')
            self.assertEqual(store.videos(), [])
            self.assertEqual(store.uploads(), [])
            self.assertIsNone(store.delete_video(vid))


if __name__ == '__main__':
    unittest.main()
