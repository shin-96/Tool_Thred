import tempfile
import unittest
from pathlib import Path

from PIL import Image

from threadstudio.render import run, probe
from threadstudio.editing import media_info, normalize, keyframe_state, chroma_key, edit_video, preview_frame


class ProEditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); cls.root = Path(cls.tmp.name)
        cls.source = cls.root / 'base.mp4'; cls.music = cls.root / 'music.mp3'
        cls.image = cls.root / 'meme.png'; cls.green = cls.root / 'green.mp4'
        run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=720x1280:r=30:d=3',
             '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo', '-t', '3', '-c:v', 'libx264',
             '-threads', '2', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', cls.source])
        run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3',
             '-c:a', 'libmp3lame', cls.music])
        run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=green:s=360x360:r=30:d=2',
             '-t', '2', '-c:v', 'libx264', '-threads', '2', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', cls.green])
        Image.new('RGBA', (100, 100), (255, 0, 0, 255)).save(cls.image)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_audio_media_info_and_mode(self):
        info = media_info(self.music)
        self.assertTrue(info['audio_only']); self.assertTrue(info['audio']); self.assertGreater(info['duration'], 2.5)
        edits, total = normalize([{'path': str(self.music), 'mode': 'overlay', 'start': 0, 'duration': 2, 'volume': 1}], 3)
        self.assertEqual(edits[0]['mode'], 'audio'); self.assertAlmostEqual(total, 3)

    def test_keyframe_interpolation_and_fade(self):
        item = {'x': 0, 'y': 0, 'width': 100, 'opacity': 1, 'rotation': 0, 'duration': 2,
                'fade_in': 1, 'keyframes': [{'t': 0, 'x': 0, 'width': 100}, {'t': 2, 'x': 200, 'width': 300}]}
        mid = keyframe_state(item, 1)
        self.assertAlmostEqual(mid['x'], 100); self.assertAlmostEqual(mid['width'], 200)
        self.assertAlmostEqual(mid['opacity'], 1)  # fade_in done at t=1
        self.assertAlmostEqual(keyframe_state(item, 0)['opacity'], 0)  # fade_in starts transparent
        self.assertAlmostEqual(keyframe_state(item, 5)['x'], 200)  # clamps after last keyframe

    def test_keyframe_and_chroma_validation(self):
        with self.assertRaises(ValueError):
            normalize([{'path': str(self.image), 'start': 0, 'duration': 1, 'keyframes': [{'t': 5, 'x': 0}]}], 3)
        with self.assertRaises(ValueError):
            normalize([{'path': str(self.image), 'start': 0, 'duration': 1, 'chroma': {'color': 'green'}}], 3)
        edits, _ = normalize([{'path': str(self.image), 'start': 0, 'duration': 1,
                               'chroma': {'color': '#00ff00', 'similarity': 0.3}}], 3)
        self.assertEqual(edits[0]['chroma']['color'], '#00ff00')

    def test_chroma_key_removes_green_keeps_red(self):
        green = Image.new('RGBA', (10, 10), (0, 255, 0, 255))
        self.assertLess(chroma_key(green, {'color': '#00ff00', 'similarity': 0.35, 'blend': 0.15}).getpixel((5, 5))[3], 30)
        red = Image.new('RGBA', (10, 10), (255, 0, 0, 255))
        self.assertGreater(chroma_key(red, {'color': '#00ff00', 'similarity': 0.35, 'blend': 0.15}).getpixel((5, 5))[3], 200)

    def test_edit_video_with_audio_keyframes_and_chroma(self):
        out = self.root / 'edited.mp4'
        items = [
            {'path': str(self.music), 'start': 0, 'duration': 3, 'volume': 0.8, 'fade_in': 0.5},
            {'path': str(self.image), 'mode': 'overlay', 'start': 0, 'duration': 2, 'x': 0, 'y': 0, 'width': 100,
             'keyframes': [{'t': 0, 'x': 0, 'y': 0, 'width': 100}, {'t': 2, 'x': 400, 'y': 400, 'width': 200}]},
            {'path': str(self.green), 'mode': 'overlay', 'start': 0, 'duration': 2, 'x': 40, 'y': 850, 'width': 280,
             'chroma': {'color': '#00ff00', 'similarity': 0.35, 'blend': 0.15}},
        ]
        edit_video(self.source, out, items, log=lambda _: None)
        info = probe(out)
        self.assertAlmostEqual(float(info['format']['duration']), 3, delta=0.3)
        self.assertTrue(any(s['codec_type'] == 'audio' for s in info['streams']))
        # Preview at t=1: keyframed red square sits near x=200..400,y=200..400 -> red-ish pixel at (300,300)
        im, total = preview_frame(self.source, items, 1)
        r, g, b = im.convert('RGB').getpixel((300, 300))
        self.assertGreater(r, 150); self.assertLess(g, 100)
        # Chroma: greenscreen area must stay blue (keyed out), not green
        r, g, b = im.convert('RGB').getpixel((100, 900))
        self.assertGreater(b, 100); self.assertLess(g, 120)


if __name__ == '__main__':
    unittest.main()
