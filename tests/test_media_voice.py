import base64
import io
import json
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from threadstudio.render import run,probe,render
from threadstudio.editing import edit_video,preview_frame,normalize
from threadstudio.voice_api import KINDS,save_profile,public_profile,request_audio,synthesize_api
from threadstudio.store import Store


def wav_bytes():
    data=io.BytesIO()
    with wave.open(data,'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000)
        f.writeframes(b''.join(struct.pack('<h',int(3500*math.sin(i*2*math.pi*440/24000))) for i in range(24000)))
    return data.getvalue()


class Reply:
    status_code=200
    def __init__(self,content=b'',data=None):self.content=content;self.data=data
    def json(self):return self.data


class VoiceSession:
    def __init__(self,reply=None):self.reply=reply or Reply(wav_bytes());self.calls=[]
    def post(self,url,**kw):self.calls.append((url,kw));return self.reply
    def get(self,url,**kw):self.calls.append((url,kw));return Reply(wav_bytes())


class VoiceApiTests(unittest.TestCase):
    def test_key_not_in_snapshot_and_destination_cannot_reuse_old_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite');profile={'name':'Test','kind':KINDS[0],'endpoint':'https://example.test/v1/audio/speech','voice':'coral','model':'tts','key_header':'Authorization','key_prefix':'Bearer '}
            pid=save_profile(store,profile,'TEST-SECRET');saved=store.get_setting('voice_apis')[pid];snapshot=public_profile(saved)
            self.assertNotIn('secret',snapshot);self.assertNotIn('TEST-SECRET',json.dumps(store.get_setting('voice_apis')))
            profile['endpoint']='https://other.test/tts'
            with self.assertRaises(ValueError):save_profile(store,profile,profile_id=pid)
            session=VoiceSession();synthesize_api('Test API cache '+tmp,snapshot,Path(tmp)/'audio.mp3',store=store,session=session,log=lambda _:None)
            self.assertEqual(session.calls[0][1]['headers']['Authorization'],'Bearer TEST-SECRET')
            self.assertTrue(Path(tmp,'audio.mp3').exists())
            self.assertEqual(probe(Path(tmp)/'audio.mp3')['streams'][0]['codec_name'],'mp3')

    def test_provider_payloads_and_xml_escaping(self):
        session=VoiceSession()
        for kind in KINDS[:3]:
            p={'kind':kind,'endpoint':'https://example.test/tts/{voice}','voice':'vi-VN-HoaiMyNeural','model':'m','speed':1,'key_header':'x-key','key_prefix':''}
            result=request_audio(p,'SECRET','Chào <bạn> & "world"',session=session);self.assertGreater(len(result),100)
            kw=session.calls[-1][1]
            self.assertFalse(kw['allow_redirects'])
            if kind==KINDS[2]:self.assertIn(b'&lt;b',kw['data']);self.assertIn(b'&amp;',kw['data'])
            else:self.assertIn('json',kw)

    def test_custom_json_url_receives_no_key_and_base64_decodes(self):
        p={'kind':KINDS[3],'endpoint':'https://example.test/tts','key_header':'Authorization','key_prefix':'Bearer ','body':{'message':'{text}'},'response':'url','response_path':'data.audio'}
        s=VoiceSession(Reply(data={'data':{'audio':'https://cdn.example.test/audio.wav'}}));request_audio(p,'SECRET','A "quoted"\nline',s)
        self.assertNotIn('headers',s.calls[-1][1]);self.assertEqual(s.calls[0][1]['json']['message'],'A "quoted"\nline')
        p['response']='base64';s=VoiceSession(Reply(data={'data':{'audio':base64.b64encode(wav_bytes()).decode()}}));self.assertEqual(request_audio(p,'SECRET','x',s),wav_bytes())


class EditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name);cls.source=cls.root/'base.mp4';cls.clip=cls.root/'reaction.mp4';cls.image=cls.root/'meme.png'
        run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=720x1280:r=30:d=4','-f','lavfi','-i','anullsrc=r=44100:cl=stereo','-t','4','-c:v','libx264','-threads','2','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac',cls.source])
        run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=red:s=360x640:r=30:d=1','-f','lavfi','-i','sine=frequency=660:duration=1','-t','1','-c:v','libx264','-threads','2','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac',cls.clip]);Image.new('RGBA',(100,100),(0,255,0,255)).save(cls.image)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_insert_retains_original_and_overlay_matches_preview(self):
        import cv2
        items=[{'path':str(self.clip),'mode':'insert','start':1,'duration':1,'audio':True},{'path':str(self.image),'mode':'overlay','start':3,'duration':1,'x':100,'y':100,'width':100,'opacity':.5}]
        out=self.root/'edited.mp4';edit_video(self.source,out,items,log=lambda _:None)
        self.assertAlmostEqual(float(probe(out)['format']['duration']),5,delta=.15)
        c=cv2.VideoCapture(str(out))
        for t,dominant in [(.5,2),(1.5,0),(2.5,2)]:
            c.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=c.read();self.assertTrue(ok);rgb=frame[600,300,::-1];self.assertGreater(int(rgb[dominant]),200)
        c.set(cv2.CAP_PROP_POS_MSEC,3500);ok,frame=c.read();c.release();self.assertTrue(ok)
        preview,_=preview_frame(self.source,items,3.5);expected=preview.convert('RGB').getpixel((140,140));actual=frame[140,140,::-1]
        for a,b in zip(actual,expected):self.assertLess(abs(int(a)-b),14)

    def test_no_overwrite_and_invalid_scene(self):
        with self.assertRaises(ValueError):edit_video(self.source,self.source,[{'path':str(self.image)}])
        with self.assertRaises(ValueError):normalize([{'path':str(self.image),'scene':5}],4,[])
        with self.assertRaises(ValueError):normalize([{'path':str(self.image),'start':3,'duration':2}],4)

    def test_render_pipeline_applies_media(self):
        import cv2
        output=self.root/'threads_overlay.mp4';render({'posts':[{'username':'demo','text':'Kiểm tra meme trong video.'}]},output,style='grid',speech=False,edits=[{'path':str(self.image),'start':0,'duration':2,'x':50,'y':1000,'width':100}],log=lambda _:None)
        c=cv2.VideoCapture(str(output));c.set(cv2.CAP_PROP_POS_MSEC,1000);ok,frame=c.read();c.release();self.assertTrue(ok);self.assertGreater(int(frame[1040,90,1]),210)


if __name__=='__main__':unittest.main()
