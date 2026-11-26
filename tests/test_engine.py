import json
import tempfile
import threading
import unittest
from pathlib import Path

from PIL import Image, ImageDraw
from threadstudio.render import pages, measure, composite, card, render, Cancelled
from threadstudio.source import validate_url


class EngineTests(unittest.TestCase):
    def test_pagination_keeps_all_words_and_fits_card(self):
        text=('Tiếng Việt có dấu, bình luận rất dài 💡 và emoji 😅.\n'*35)+'https://example.com/'+('a'*180)
        post={'username':'tester','text':text}
        chunks=pages(post,9,22)
        self.assertGreater(len(chunks),3)
        # Long URLs may split, but all non-whitespace content must survive.
        self.assertEqual(''.join(text.split()),''.join(''.join(lines).replace(' ','') for lines in chunks))
        draw=ImageDraw.Draw(Image.new('RGB',(1,1)))
        self.assertTrue(all(measure(draw,line,22)<=548.5 for lines in chunks for line in lines))
        with tempfile.TemporaryDirectory() as tmp:
            cache=Path(tmp)
            for style in ['center','top','grid']:
                c=card(post,chunks[0],0,len(chunks),cache,22)
                frame=composite(c,style,c if style=='grid' else None)
                self.assertEqual(frame.size,(720,1280))
                if style=='grid':self.assertLess(140+c.height+40+c.height,1210)

    def test_threads_url_validation(self):
        self.assertEqual(validate_url('https://www.threads.net/@user/post/ABC?x=1'),'https://www.threads.com/@user/post/ABC')
        for url in ['file:///C:/secret','https://threads.com.evil.org/@x/post/a','http://threads.com/@x/post/a','https://threads.com/login']:
            with self.assertRaises(ValueError):validate_url(url)

    def test_cancel_does_not_publish_partial_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'cancel.mp4';event=threading.Event();event.set()
            with self.assertRaises(Cancelled):
                render({'posts':[{'username':'a','text':'Test cancellation'}]},output,style='grid',speech=False,cancel=event,log=lambda _:None)
            self.assertFalse(output.exists())

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'existing.mp4';p.write_bytes(b'existing')
            with self.assertRaises(ValueError):render({'posts':[{'username':'a','text':'Test'}]},p,style='grid',speech=False)
            self.assertEqual(p.read_bytes(),b'existing')


if __name__=='__main__':unittest.main()
