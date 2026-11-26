import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from threadstudio.store import Store
from threadstudio.production import ProductionQueue
from threadstudio.tiktok import TikTokAPI,TikTokError,chunk_plan
from threadstudio.source import metadata_post,EXTRACT
from threadstudio.secrets import protect,unprotect


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=Store(self.root/'test.db')
    def tearDown(self):self.tmp.cleanup()
    def add(self):return self.store.add_job('demo','source',{'speech':False},{'posts':[{'username':'u','text':'Test'}]},self.root)

    def test_restart_does_not_auto_retry_upload(self):
        jid=self.add();self.store.update_job(jid,status='rendering')
        uid=self.store.new_upload('v','a','direct','caption');self.store.update_upload(uid,'uploading',publish_id='pid')
        self.store.recover();self.assertEqual(self.store.job(jid)['status'],'interrupted');self.assertEqual(self.store.uploads()[0]['status'],'unknown')
        with self.assertRaises(ValueError):self.store.new_upload('v','a','direct','caption')
        self.store.retry(jid);self.assertEqual(self.store.job(jid)['status'],'queued')

    def test_atomic_claim_and_snapshot(self):
        opts={'speech':False};data={'posts':[{'text':'original','username':'u'}]}
        jid=self.store.add_job('demo','source',opts,data,self.root);opts['speech']=True;data['posts'][0]['text']='changed'
        results=[]
        threads=[threading.Thread(target=lambda:results.append(self.store.claim())) for _ in range(8)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(sum(bool(r) for r in results),1)
        job=self.store.job(jid);self.assertFalse(json.loads(job['options'])['speech']);self.assertEqual(json.loads(job['data'])['posts'][0]['text'],'original')

    def test_pause_parallelism_and_cancel_queued(self):
        active=0;peak=0;lock=threading.Lock();gate=threading.Event()
        def renderer(data,output,**kw):
            nonlocal active,peak
            with lock:active+=1;peak=max(peak,active)
            gate.wait(5);Path(output).write_bytes(b'video')
            with lock:active-=1
            return output
        for _ in range(4):self.add()
        with patch('threadstudio.production.video_metadata',return_value={'duration':1}):
            q=ProductionQueue(self.store,2,renderer=renderer)
            try:
                time.sleep(.4);self.assertEqual(peak,0);q.start()
                deadline=time.monotonic()+5
                while peak<2 and time.monotonic()<deadline:time.sleep(.05)
                self.assertEqual(peak,2);q.pause()
                for job in self.store.jobs():
                    if job['status']=='queued':q.cancel(job['id'])
                gate.set();deadline=time.monotonic()+5
                while len(self.store.videos())<2 and time.monotonic()<deadline:time.sleep(.05)
                self.assertEqual(len(self.store.videos()),2);self.assertEqual(sum(j['status']=='cancelled' for j in self.store.jobs()),2)
            finally:
                gate.set();q.shutdown();q.thread.join(3)

    def test_secrets_roundtrip(self):
        encrypted=protect('unit-test-token');self.assertNotIn('unit-test-token',encrypted);self.assertEqual(unprotect(encrypted),'unit-test-token')


class Response:
    def __init__(self,data,status=200):self.data=data;self.status_code=status;self.ok=status<400
    def json(self):return self.data


class FakeAPI:
    def __init__(self):self.calls=[];self.blocks=[]
    def post(self,url,**kw):
        self.calls.append((url,kw))
        return Response({'error':{'code':'ok'},'data':{'publish_id':'pid123','upload_url':'https://open-upload.tiktokapis.com/video/test'}})
    def put(self,url,**kw):self.blocks.append(kw);return Response({},201)


class TikTokTests(unittest.TestCase):
    def test_chunk_remainder_has_no_data_loss(self):
        for size in [1,4*1024**2,10*1024**2,11*1024**2,25*1024**2+7,4*1024**3]:
            chunk,count=chunk_plan(size);last=size-chunk*(count-1)
            self.assertEqual(chunk*(count-1)+last,size);self.assertGreater(last,0);self.assertLessEqual(last,128*1024**2);self.assertLessEqual(count,1000)

    @patch('threadstudio.tiktok.probe',return_value={'format':{'duration':'30'},'streams':[{'codec_type':'video','width':720,'height':1280}]})
    def test_upload_tracks_publish_id_before_bytes_and_validates_privacy(self,_):
        fake=FakeAPI();api=TikTokAPI('fake-token',fake)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'v.mp4';p.write_bytes(b'12345');ids=[]
            api.upload(p,'caption',on_init=ids.append)
            self.assertEqual(ids,['pid123']);self.assertEqual(fake.blocks[0]['data'],b'12345');self.assertEqual(fake.blocks[0]['headers']['Content-Range'],'bytes 0-4/5')
            with self.assertRaises(ValueError):api.upload(p,'caption','direct',privacy='PUBLIC_TO_EVERYONE',creator={'privacy_level_options':['SELF_ONLY']})
            self.assertEqual(len(fake.calls),1)
            self.assertNotIn('post_info',fake.calls[0][1]['json'])

    def test_network_init_is_uncertain(self):
        import requests
        class Broken:
            def post(self,*a,**kw):raise requests.Timeout('secret-must-not-be-echoed')
        with self.assertRaises(TikTokError) as e:TikTokAPI('token',Broken()).creator()
        self.assertTrue(e.exception.uncertain);self.assertNotIn('secret-must',str(e.exception))

    def test_metadata_fallback_and_url_identity(self):
        url='https://www.threads.com/@demo/post/ABC'
        html='<meta property="og:url" content="'+url+'"><meta property="og:description" content="Nội dung thật &amp; có dấu">'
        self.assertEqual(metadata_post(html,url)['text'],'Nội dung thật & có dấu')
        self.assertIsNone(metadata_post(html,url.replace('ABC','OTHER')))
        self.assertIn('canonical',EXTRACT)


class BrowserWorkflowTests(unittest.TestCase):
    def test_media_link_is_same_post_and_upload_form_keeps_caption(self):
        from playwright.sync_api import sync_playwright
        from threadstudio.browser_publish import prepare_page
        with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
            browser=p.chromium.launch(channel='msedge',headless=True)
            try:
                page=browser.new_page();page.route('https://fixture.test/**',lambda route:route.fulfill(body='<html></html>',content_type='text/html'));page.goto('https://fixture.test/')
                page.set_content('''<div><a href="https://www.threads.com/@demo/post/ABC"><time>1h</time></a><span dir="auto">Nội dung bài có ảnh</span><a href="https://www.threads.com/@demo/post/ABC/media">ảnh</a><button>1</button><button>2</button><button>3</button><button>4</button></div>''')
                posts=page.evaluate(EXTRACT);self.assertEqual(len(posts),1);self.assertEqual(posts[0]['username'],'demo');self.assertIn('Nội dung bài có ảnh',posts[0]['text'])
                page.set_content('<input type="file"><div contenteditable="true" role="textbox"></div><button>Post</button>')
                path=Path(tmp)/'sample.mp4';path.write_bytes(b'test');prepare_page(page,path,'Caption tiếng Việt #threads')
                self.assertEqual(page.locator('input').evaluate('(el)=>el.files[0].name'),'sample.mp4');self.assertEqual(page.locator('[contenteditable]').inner_text(),'Caption tiếng Việt #threads')
            finally:browser.close()


if __name__=='__main__':unittest.main()
