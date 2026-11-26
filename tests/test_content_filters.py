import json
import tempfile
import unittest
from pathlib import Path

from threadstudio.comment_filter import auto_pick, is_ad, parse_likes, select_posts
from threadstudio.speech_text import expand_speech


class AdFilterTests(unittest.TestCase):
    def test_ads_detected(self):
        for text in ['Mua ở đây nè https://shopee.vn/abc giá rẻ lắm',
                     'Ai cần thì ib mình để được tư vấn giá nha',
                     'Liên hệ zalo 0912345678 để đặt hàng',
                     'Áo này 199k/sp, freeship toàn quốc, chốt đơn nhanh tay',
                     'Sản phẩm chính hãng 100%, bảo hành 12 tháng, đăng ký ngay']:
            self.assertTrue(is_ad(text), text)

    def test_normal_comments_kept(self):
        for text in ['Đọc mà cười xỉu luôn á 😂😂', 'Thật không vậy trời, ko tin được',
                     'Mình cũng từng bị như này, sợ vãi', 'Cái kết không ai ngờ tới haha']:
            self.assertFalse(is_ad(text), text)

    def test_parse_likes(self):
        self.assertEqual(parse_likes({'stats': ['Like 1.2K', 'Comment 3']}), 1200)
        self.assertEqual(parse_likes({'stats': ['Like 45']}), 45)
        self.assertEqual(parse_likes({'stats': []}), 0)

    def test_select_posts_funny_first_ads_dropped(self):
        posts = [{'username': 'op', 'text': 'Bài gốc'},
                 {'username': 'ad', 'text': 'Mua ngay tại shopee.vn giá chỉ 99k', 'stats': ['Like 999']},
                 {'username': 'funny', 'text': 'Cười xỉu với cái kết này 😂😂😂', 'stats': ['Like 500']},
                 {'username': 'plain', 'text': 'Ừ đúng rồi', 'stats': ['Like 2']},
                 {'username': 'mid', 'text': 'Haha cái này hài thật sự luôn á mọi người ơi', 'stats': ['Like 50']}]
        picked = select_posts(posts, 3, funny_only=True)
        self.assertEqual([p['username'] for p in picked], ['op', 'funny', 'mid'])
        plain = select_posts(posts, 3, funny_only=False)
        self.assertEqual([p['username'] for p in plain], ['op', 'ad', 'funny'])


    def test_auto_pick_matches_auto_mode_and_drops_seeding(self):
        posts = [{'username': 'main', 'text': 'Bài gốc', 'stats': ['Like 10']},
                 {'username': 'ad', 'text': 'áo khoác 195k quảng cáo', 'stats': ['Like 999']},
                 {'username': 'fun', 'text': 'cười xỉu luôn 😂', 'stats': ['Like 5']},
                 {'username': 'mid', 'text': 'cũng được đó mọi người ơi', 'stats': ['Like 1']}]
        picked = auto_pick(posts, 3)
        self.assertEqual(picked, {id(posts[2]), id(posts[3])})


class SpeechTextTests(unittest.TestCase):
    def test_abbreviations(self):
        self.assertEqual(expand_speech('ko đi đc đâu'), 'không đi được đâu')
        self.assertIn('nhắn tin', expand_speech('có gì ib mình nha'))
        self.assertIn('mọi người', expand_speech('mn ơi cho hỏi'))
        self.assertIn('gì', expand_speech('là j vậy'))

    def test_numbers_and_units(self):
        self.assertIn('500 nghìn', expand_speech('cái này 500k'))
        self.assertIn('4 triệu', expand_speech('lương 4tr'))
        self.assertIn('1 mét 8', expand_speech('cao 1m8'))
        self.assertIn('50 phần trăm', expand_speech('giảm 50%'))

    def test_emoji_stripped(self):
        out = expand_speech('cười xỉu 😂😂 luôn á')
        self.assertNotIn('😂', out)


class RenderFilterIntegrationTests(unittest.TestCase):
    def test_render_funny_only_picks_funny_and_expands_speech(self):
        from threadstudio.render import render
        data = {'posts': [
            {'username': 'op', 'text': 'Bài gốc: ko ai tin đc chuyện này', 'date': '', 'avatar': '', 'stats': []},
            {'username': 'ad', 'text': 'Mua ngay shopee.vn giảm giá 50% chốt đơn', 'date': '', 'avatar': '', 'stats': ['Like 999']},
            {'username': 'funny', 'text': 'Cười xỉu luôn á mn 😂 cái kết 500k', 'date': '', 'avatar': '', 'stats': ['Like 300']},
            {'username': 'plain', 'text': 'Ừ', 'date': '', 'avatar': '', 'stats': []}]}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'v.mp4'
            render(data, out, speech=False, funny_only=True, max_posts=2, log=lambda _: None)
            timeline = json.loads((Path(tmp) / 'v_project' / 'timeline.json').read_text(encoding='utf8'))
            self.assertEqual([t['author'] for t in timeline], ['op', 'funny'])
            self.assertIn('không ai tin được', timeline[0]['spoken'])
            self.assertIn('500 nghìn', timeline[1]['spoken'])
            self.assertIn('ko ai tin đc', timeline[0]['text'])  # card text stays original


if __name__ == '__main__':
    unittest.main()
