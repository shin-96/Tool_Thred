"""Durable local production catalog; no network calls and no plaintext credentials."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .render import ROOT


def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Store:
    def __init__(self,path=None):
        self.path=Path(path or ROOT/'data'/'studio.db');self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,title TEXT NOT NULL,source TEXT NOT NULL,data TEXT,options TEXT NOT NULL,output TEXT NOT NULL,status TEXT NOT NULL,progress REAL DEFAULT 0,message TEXT DEFAULT '',created TEXT NOT NULL,updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS videos(id TEXT PRIMARY KEY,job_id TEXT UNIQUE,title TEXT NOT NULL,path TEXT UNIQUE NOT NULL,caption TEXT DEFAULT '',duration REAL DEFAULT 0,width INTEGER DEFAULT 0,height INTEGER DEFAULT 0,thumbnail TEXT DEFAULT '',created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY,video_id TEXT NOT NULL,account TEXT NOT NULL,mode TEXT NOT NULL,caption TEXT NOT NULL,status TEXT NOT NULL,publish_id TEXT DEFAULT '',message TEXT DEFAULT '',created TEXT NOT NULL,updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT,message TEXT NOT NULL,created TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.path,timeout=20);c.row_factory=sqlite3.Row
        try:
            c.execute('PRAGMA journal_mode=WAL')
            with c:yield c
        finally:c.close()

    def rows(self,sql,args=()):
        with self.connect() as c:return [dict(r) for r in c.execute(sql,args).fetchall()]

    def execute(self,sql,args=()):
        with self.connect() as c:c.execute(sql,args)

    def get_setting(self,key,default=None):
        rows=self.rows('SELECT value FROM settings WHERE key=?',(key,));return json.loads(rows[0]['value']) if rows else default

    def setting(self,key,value):self.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))

    def add_job(self,title,source,options,data=None,output_dir=None):
        jid=uuid.uuid4().hex;directory=Path(output_dir or ROOT/'outputs');directory.mkdir(parents=True,exist_ok=True)
        safe=''.join(c if c.isalnum() or c in '-_' else '_' for c in title)[:55] or 'video'
        output=str((directory/(safe+'_'+jid[:8]+'.mp4')).resolve());stamp=now()
        self.execute('INSERT INTO jobs(id,title,source,data,options,output,status,created,updated) VALUES(?,?,?,?,?,?,?,?,?)',(jid,title,source,json.dumps(data,ensure_ascii=False) if data else None,json.dumps(options),output,'queued',stamp,stamp));return jid

    def jobs(self):return self.rows('SELECT * FROM jobs ORDER BY created DESC,rowid DESC')
    def videos(self):return self.rows('SELECT * FROM videos ORDER BY created DESC,rowid DESC')
    def uploads(self):return self.rows('SELECT u.*,v.title FROM uploads u LEFT JOIN videos v ON u.video_id=v.id ORDER BY u.created DESC,u.rowid DESC')
    def job(self,jid):
        rows=self.rows('SELECT * FROM jobs WHERE id=?',(jid,));return rows[0] if rows else None

    def update_job(self,jid,**fields):
        allowed={'status','progress','message','data'}
        if not set(fields)<=allowed:raise ValueError('Invalid job fields')
        fields['updated']=now()
        self.execute('UPDATE jobs SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),jid))

    def log(self,jid,message):
        self.execute('INSERT INTO logs(job_id,message,created) VALUES(?,?,?)',(jid,str(message),now()))
        self.update_job(jid,message=str(message))

    def recover(self):
        self.execute("UPDATE jobs SET status='interrupted',message='Ứng dụng đã đóng giữa tác vụ. Chọn Thử lại để tiếp tục.',updated=? WHERE status IN ('fetching','rendering')",(now(),))
        self.execute("UPDATE uploads SET status='unknown',message='Phiên trước bị gián đoạn. Kiểm tra TikTok hoặc tra cứu publish_id trước khi gửi lại.',updated=? WHERE status IN ('initializing','uploading')",(now(),))

    def claim(self):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            r=c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created,rowid LIMIT 1").fetchone()
            if not r:return None
            c.execute("UPDATE jobs SET status='fetching',updated=? WHERE id=?",(now(),r['id']));return dict(r)

    def retry(self,jid):
        self.execute("UPDATE jobs SET status='queued',progress=0,message='',updated=? WHERE id=? AND status IN ('failed','cancelled','interrupted')",(now(),jid))

    def add_video(self,path,title,meta,job_id=None):
        path=str(Path(path).resolve());vid=uuid.uuid4().hex
        self.execute('INSERT OR IGNORE INTO videos(id,job_id,title,path,caption,duration,width,height,thumbnail,created) VALUES(?,?,?,?,?,?,?,?,?,?)',(vid,job_id,title,path,meta.get('caption',title),meta.get('duration',0),meta.get('width',0),meta.get('height',0),meta.get('thumbnail',''),now()))
        return self.rows('SELECT id FROM videos WHERE path=?',(path,))[0]['id']

    def delete_video(self,vid):
        rows=self.rows('SELECT * FROM videos WHERE id=?',(vid,))
        if not rows:return None
        self.execute('DELETE FROM uploads WHERE video_id=?',(vid,))
        self.execute('DELETE FROM videos WHERE id=?',(vid,))
        return rows[0]

    def new_upload(self,video_id,account,mode,caption):
        # Block duplicate or unresolved submissions, including after app restart.
        existing=self.rows("SELECT id FROM uploads WHERE video_id=? AND account=? AND status NOT IN ('failed','cancelled')",(video_id,account))
        if existing:raise ValueError('Video đã gửi hoặc đang chờ kiểm tra trên tài khoản này. Xem lịch sử trước khi gửi lại.')
        uid=uuid.uuid4().hex;stamp=now()
        self.execute('INSERT INTO uploads(id,video_id,account,mode,caption,status,created,updated) VALUES(?,?,?,?,?,?,?,?)',(uid,video_id,account,mode,caption,'initializing',stamp,stamp));return uid

    def update_upload(self,uid,status,message='',publish_id=None):
        if publish_id is None:self.execute('UPDATE uploads SET status=?,message=?,updated=? WHERE id=?',(status,message,now(),uid))
        else:self.execute('UPDATE uploads SET status=?,message=?,publish_id=?,updated=? WHERE id=?',(status,message,publish_id,now(),uid))
