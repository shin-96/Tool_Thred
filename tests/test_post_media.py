import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import threadstudio.source as source_module
from threadstudio.render import render, run


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        yield self.content


class AttachMediaTests(unittest.TestCase):
    def test_downloads_and_records_path(self):
        data = {'posts': [{'username': 'op', 'text': 'x',
                            'media': {'type': 'image', 'url': 'https://cdn.example/pic.jpg'}}]}
        with mock.patch.object(source_module.requests, 'get', return_value=FakeResponse(b'\xff\xd8fake')):
            source_module.attach_media(data, log=lambda m: None)
        media = data['posts'][0]['media']
        self.assertIn('path', media)
        self.assertTrue(Path(media['path']).is_file())
        Path(media['path']).unlink(missing_ok=True)

    def test_poster_disguised_as_video_is_dropped(self):
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / 'p.png'
            Image.new('RGB', (64, 64), (200, 0, 0)).save(png)
            data = {'posts': [{'username': 'op', 'text': 'x',
                                'media': {'type': 'video', 'url': 'https://cdn.example/poster.mp4'}}]}
            with mock.patch.object(source_module.requests, 'get', return_value=FakeResponse(png.read_bytes())):
                source_module.attach_media(data, log=lambda m: None)
            self.assertNotIn('media', data['posts'][0])

    def test_image_that_is_really_video_is_upgraded(self):
        with tempfile.TemporaryDirectory() as td:
            clip = Path(td) / 'c.mp4'
            run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=64x64:r=30:d=1',
                 '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(clip)])
            data = {'posts': [{'username': 'op', 'text': 'x',
                                'media': {'type': 'image', 'url': 'https://cdn.example/clip.jpg'}}]}
            with mock.patch.object(source_module.requests, 'get', return_value=FakeResponse(clip.read_bytes())):
                source_module.attach_media(data, log=lambda m: None)
            media = data['posts'][0]['media']
            self.assertEqual(media['type'], 'video')
            self.assertTrue(Path(media['path']).is_file())
            Path(media['path']).unlink(missing_ok=True)

    def test_failed_download_drops_media(self):
        data = {'posts': [{'username': 'op', 'text': 'x',
                            'media': {'type': 'video', 'url': 'https://cdn.example/v.mp4'}}]}
        with mock.patch.object(source_module.requests, 'get', side_effect=RuntimeError('boom')):
            source_module.attach_media(data, log=lambda m: None)
        self.assertNotIn('media', data['posts'][0])


class CapturedVideoTests(unittest.TestCase):
    def test_captured_mp4_goes_to_video_posts_only(self):
        posts = [
            {'username': 'op', 'has_video': True, 'media': {'type': 'image', 'url': 'https://cdn/poster.jpg'}},
            {'username': 'photo', 'has_video': False, 'media': {'type': 'image', 'url': 'https://cdn/pic.jpg'}},
            {'username': 'clip', 'has_video': True},
        ]
        source_module.apply_captured_videos(posts, ['https://scontent/v1.mp4', 'https://scontent/v2.mp4'])
        self.assertEqual(posts[0]['media'], {'type': 'video', 'url': 'https://scontent/v1.mp4'})
        self.assertEqual(posts[1]['media'], {'type': 'image', 'url': 'https://cdn/pic.jpg'})
        self.assertEqual(posts[2]['media'], {'type': 'video', 'url': 'https://scontent/v2.mp4'})


class RenderMediaTests(unittest.TestCase):
    def test_media_plays_in_box_under_card(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            red = root / 'red.jpg'
            Image.new('RGB', (720, 1280), (220, 30, 30)).save(red)
            data = {'url': 'https://www.threads.com/@x/post/abc', 'posts': [
                {'username': 'op', 'text': 'Bài gốc có ảnh đỏ kèm theo nè mọi người ơi', 'stats': [],
                 'media': {'type': 'image', 'url': 'https://example.com/red.jpg', 'path': str(red)}},
                {'username': 'plain', 'text': 'Bình luận thường không có gì kèm theo cả nhé', 'stats': []}]}
            out = render(data, str(root / 'out.mp4'), speech=False, log=lambda m: None)
            frame = subprocess.run(['ffmpeg', '-v', 'error', '-ss', '1', '-i', out, '-frames:v', '1',
                                    '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
            def px(x, y):
                i = (y * 720 + x) * 3
                return frame[i], frame[i + 1], frame[i + 2]
            r, g, b = px(360, 1000)  # centre of the media box under the card: the red image
            self.assertGreater(r, 150)
            self.assertLess(g, 90)
            self.assertLess(b, 90)
            r, g, b = px(6, 1274)  # frame corner stays gameplay, NOT the media
            self.assertFalse(r > 150 and g < 90 and b < 90)


if __name__ == '__main__':
    unittest.main()
