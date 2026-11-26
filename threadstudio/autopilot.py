"""Auto mode: poll a Google Doc for new Threads links on a fixed interval, queue
them for rendering with a saved template snapshot, then post finished videos to
TikTok on a fixed posting interval (e.g. one video per hour).

State lives in the store settings so a restart resumes where it left off: links
already seen are never queued twice, and a video already sent (or awaiting a
status check) on the chosen account is never sent again — the uploads table's
own duplicate guard is the second line of defence."""
import threading
import time

from .doclinks import extract_links, fetch_doc_text

TICK_SECONDS = 15


class AutoPilot:
    def __init__(self, store, queue, api_factory, notify=lambda text: None):
        self.store = store
        self.queue = queue
        self.api_factory = api_factory  # account name -> TikTokAPI
        self.notify = notify
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None

    def config(self):
        return self.store.get_setting('autopilot', {})

    def state(self):
        return self.store.get_setting('autopilot_state', {'seen': [], 'jobs': [], 'next_scan': 0, 'next_upload': 0, 'last_message': ''})

    def _save_state(self, st):
        self.store.setting('autopilot_state', st)

    def _say(self, text):
        st = self.state()
        st['last_message'] = text
        self._save_state(st)
        self.notify(text)

    def start(self, config):
        config = dict(config, enabled=True)
        self.store.setting('autopilot', config)
        st = self.state()
        st['next_scan'] = 0  # scan right away
        st.setdefault('next_upload', time.time())
        self._save_state(st)
        self.queue.start()
        if not self._thread or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        self._say('Chế độ tự động: BẬT. Đang quét Doc…')

    def resume(self):
        """Restart the loop after an app relaunch if auto mode was left on."""
        if self.config().get('enabled'):
            self.start(self.config())

    def stop(self):
        cfg = self.config()
        cfg['enabled'] = False
        self.store.setting('autopilot', cfg)
        self._stop.set()
        self._say('Chế độ tự động: TẮT.')

    def scan_now(self):
        cfg = self.config()
        if cfg.get('doc'):
            threading.Thread(target=self._guarded_scan, args=(cfg,), daemon=True).start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                cfg = self.config()
                if cfg.get('enabled'):
                    now = time.time()
                    st = self.state()
                    if now >= st.get('next_scan', 0):
                        self._guarded_scan(cfg)
                        st = self.state()
                    if now >= st.get('next_upload', 0):
                        self._upload_due(cfg, st)
            except Exception as e:  # the loop must survive any single failure
                self._say('Tự động: ' + str(e))
            self._stop.wait(TICK_SECONDS)

    def _guarded_scan(self, cfg):
        if not self._lock.acquire(blocking=False):
            return
        try:
            self._scan(cfg)
        except Exception as e:
            self._say('Tự động — quét Doc lỗi: ' + str(e))
        finally:
            self._lock.release()

    def _scan(self, cfg):
        st = self.state()
        st['next_scan'] = time.time() + max(1, int(cfg.get('poll_minutes', 15))) * 60
        self._save_state(st)
        links = extract_links(fetch_doc_text(cfg['doc']))
        seen = set(st.get('seen', []))
        existing = {j['source'] for j in self.store.jobs()}
        fresh = [u for u in links if u not in seen and u not in existing]
        for url in fresh:
            code = url.rstrip('/').split('/')[-1]
            jid = self.store.add_job('auto_' + code, url, dict(cfg['options'], autopilot=True), None, cfg.get('output_dir'))
            st.setdefault('jobs', []).append(jid)
        st['seen'] = sorted(seen | set(links))
        st['last_scan'] = time.time()
        self._save_state(st)
        if fresh:
            self._say(f'Tự động: Doc có {len(fresh)} link mới, đã thêm vào hàng đợi dựng video.')
        return fresh

    def _upload_due(self, cfg, st):
        if not cfg.get('post_to_tiktok', True):
            return  # render-only mode: videos wait in the library for manual posting
        account = cfg.get('account', '')
        jobs = set(st.get('jobs', []))
        pending = [v for v in self.store.videos() if v.get('job_id') in jobs]
        pending.sort(key=lambda v: v['created'])
        target = None
        for v in pending:
            sent = self.store.rows("SELECT id FROM uploads WHERE video_id=? AND account=? AND status NOT IN ('failed','cancelled')", (v['id'], account))
            if not sent:
                target = v
                break
        if target is None:
            return
        mode = cfg.get('mode', 'inbox')
        uid = self.store.new_upload(target['id'], account, mode, target['caption'])
        initialized = {'yes': False}
        try:
            api = self.api_factory(account)
            creator = api.creator() if mode == 'direct' else None
            privacy = cfg.get('privacy') or 'SELF_ONLY'
            if mode == 'direct':
                options = (creator or {}).get('privacy_level_options', [])
                if privacy not in options:
                    privacy = 'SELF_ONLY' if 'SELF_ONLY' in options else (options[0] if options else privacy)

            def on_init(pid):
                initialized['yes'] = True
                self.store.update_upload(uid, 'uploading', 'Đang gửi dữ liệu video.', pid)

            api.upload(target['path'], target['caption'], mode, privacy, creator, on_init,
                       post_options={'aigc': True, 'allow_comment': True})
            self.store.update_upload(uid, 'processing', 'Tự động gửi. TikTok đang xử lý; tra cứu trạng thái ở tab TikTok.')
            self._say('Tự động: đã gửi TikTok video "' + target['title'] + '". Video tiếp theo sau ' + str(cfg.get('upload_minutes', 60)) + ' phút.')
        except Exception as e:
            self.store.update_upload(uid, 'unknown' if initialized['yes'] else 'failed', str(e))
            self._say('Tự động: gửi TikTok lỗi — ' + str(e))
        st = self.state()
        st['next_upload'] = time.time() + max(1, int(cfg.get('upload_minutes', 60))) * 60
        self._save_state(st)
