import json
import threading
from pathlib import Path

from .render import ROOT, Cancelled, probe, render
from .source import fetch_thread


def video_metadata(path):
    import cv2
    path=Path(path).resolve();info=probe(path)
    stream=next((s for s in info['streams'] if s['codec_type']=='video'),None)
    if not stream:raise ValueError('Tệp không có luồng video.')
    duration=float(info['format'].get('duration',0))
    if duration<=0:raise ValueError('Video có thời lượng không hợp lệ.')
    thumbs=ROOT/'data'/'thumbnails';thumbs.mkdir(parents=True,exist_ok=True)
    import hashlib
    thumb=thumbs/(hashlib.sha256((str(path)+str(path.stat().st_mtime_ns)).encode()).hexdigest()[:24]+'.jpg')
    if not thumb.exists():
        cap=cv2.VideoCapture(str(path));cap.set(cv2.CAP_PROP_POS_MSEC,min(1.5,duration/2)*1000);ok,frame=cap.read();cap.release()
        if ok:
            h,w=frame.shape[:2];frame=cv2.resize(frame,(max(1,int(w*min(360/w,480/h))),max(1,int(h*min(360/w,480/h)))))
            cv2.imencode('.jpg',frame)[1].tofile(str(thumb))
    return {'duration':duration,'width':stream['width'],'height':stream['height'],'thumbnail':str(thumb) if thumb.exists() else ''}


class ProductionQueue:
    def __init__(self,store,workers=2,renderer=render,fetcher=fetch_thread):
        self.store=store;self.workers=max(1,min(3,int(workers)));self.renderer=renderer;self.fetcher=fetcher
        self.active={};self.lock=threading.Lock();self.enabled=False;self.stopping=False
        self.store.recover()
        self.thread=threading.Thread(target=self._dispatch,daemon=True);self.thread.start()

    def start(self):self.enabled=True
    def pause(self):self.enabled=False
    def cancel(self,jid):
        with self.lock:
            item=self.active.get(jid)
            if item:item[1].set()
            else:self.store.execute("UPDATE jobs SET status='cancelled' WHERE id=? AND status='queued'",(jid,))

    def _dispatch(self):
        while not self.stopping:
            with self.lock:
                self.active={j:v for j,v in self.active.items() if v[0].is_alive()}
                if self.enabled and len(self.active)<self.workers:
                    job=self.store.claim()
                    if job:
                        event=threading.Event();t=threading.Thread(target=self._work,args=(job,event),daemon=True)
                        self.active[job['id']]=(t,event);t.start()
            threading.Event().wait(.3)

    def _work(self,job,event):
        jid=job['id'];log=lambda text:self.store.log(jid,text)
        try:
            options=json.loads(job['options']);data=json.loads(job['data']) if job['data'] else None
            # A complete output from an interrupted session can be indexed without re-rendering.
            if Path(job['output']).is_file():
                meta=video_metadata(job['output']);self.store.add_video(job['output'],job['title'],meta,jid)
                self.store.update_job(jid,status='ready',progress=1,message='Đã khôi phục video hoàn tất.');return
            if options.get('operation')=='edit':
                from .editing import edit_video
                self.store.update_job(jid,status='rendering')
                output=edit_video(job['source'],job['output'],options['edits'],log=log,progress=lambda p:self.store.update_job(jid,progress=float(p)),cancel=event)
                meta=video_metadata(output);meta['caption']=options.get('caption',job['title'])
                self.store.add_video(output,job['title'],meta,jid);self.store.update_job(jid,status='ready',progress=1,message='Bản chỉnh sửa đã vào thư viện.');return
            if not data:
                if job['source'].startswith('https://'):
                    data=self.fetcher(job['source'],log,limit=max(30,int(options.get('max_posts',12))),cancel=event)
                else:data=json.loads(Path(job['source']).read_text(encoding='utf8'))
                self.store.update_job(jid,data=json.dumps(data,ensure_ascii=False))
            if event.is_set():raise Cancelled('Đã hủy tác vụ.')
            self.store.update_job(jid,status='rendering',progress=0)
            output=self.renderer(data,job['output'],**options,log=log,progress=lambda p:self.store.update_job(jid,progress=float(p)),cancel=event)
            title=job['title']
            try:  # name the video after what the author actually says, not the post slug
                from .titles import summarize_title,slugify_title
                summary=summarize_title(data['posts'][0]['text']) if data.get('posts') else ''
                if summary:
                    renamed=Path(output).with_name(slugify_title(summary)+'_'+jid[:8]+'.mp4')
                    if renamed!=Path(output):
                        if renamed.exists():renamed.unlink()
                        Path(output).replace(renamed);output=str(renamed);title=summary
                        self.store.execute('UPDATE jobs SET title=?,output=? WHERE id=?',(title,output,jid))
            except Exception:pass
            meta=video_metadata(output);meta['caption']=data['posts'][0]['text'][:2000]
            self.store.add_video(output,title,meta,jid);self.store.update_job(jid,status='ready',progress=1,message='Video đã vào thư viện.')
        except Cancelled as e:self.store.update_job(jid,status='cancelled',message=str(e))
        except Exception as e:self.store.update_job(jid,status='failed',message=str(e));self.store.log(jid,str(e))

    def shutdown(self):
        self.stopping=True;self.enabled=False
        with self.lock:
            active=list(self.active.values())
            for _,event in active:event.set()
        # Give FFmpeg cancellation time to terminate children before the GUI process exits.
        import time
        deadline=time.monotonic()+3
        for worker,_ in active:worker.join(max(0,deadline-time.monotonic()))
        self.thread.join(1)
