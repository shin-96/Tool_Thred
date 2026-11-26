"""Dedicated user-controlled Edge profiles, never the user's default browser profile."""
import queue
import threading
import re
from pathlib import Path

from playwright.sync_api import sync_playwright
from .render import ROOT


def prepare_page(page,path,caption):
    if len(caption.encode('utf-16-le'))//2>2200:raise ValueError('Caption quá 2200 ký tự UTF-16. Sửa caption trước khi tải.')
    file_input=page.locator('input[type="file"]')
    file_input.first.wait_for(state='attached',timeout=20000)
    file_input.first.set_input_files(str(path),timeout=120000)
    box=page.locator('[contenteditable="true"]')
    box.first.wait_for(state='visible',timeout=120000)
    box.first.fill(caption)


class BrowserPublisher:
    def __init__(self,store,notify=lambda text:None):
        self.store=store;self.notify=notify;self.commands=queue.Queue();self.thread=None;self.profile=None;self.stop=threading.Event()

    def open(self,profile='main'):
        if not re.fullmatch(r'[\w-]{1,64}',profile):raise ValueError('Tên hồ sơ từ 1–64 chữ, số, _ hoặc -.')
        if self.thread and self.thread.is_alive():
            if self.profile!=profile:raise ValueError('Đóng cửa sổ TikTok hiện tại trước khi đổi hồ sơ.')
            self.commands.put(('open',None));return
        self.profile=profile;self.stop.clear();self.commands=queue.Queue();self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()

    def prepare(self,video,caption):
        if not self.thread or not self.thread.is_alive():raise ValueError('Mở TikTok Studio và đăng nhập trong trình duyệt trước.')
        if not Path(video['path']).is_file():raise ValueError('Không tìm thấy video đã chọn.')
        if len(caption.encode('utf-16-le'))//2>2200:raise ValueError('Caption quá dài. Sửa caption trước khi tải.')
        self.commands.put(('upload',(dict(video),caption)))

    def close(self):self.stop.set()

    def _run(self):
        context=None
        try:
            with sync_playwright() as p:
                profile=ROOT/'data'/'browser_profiles'/self.profile
                context=None
                for channel in ('chrome','msedge'):  # prefer Google Chrome, fall back to Edge
                    try:
                        context=p.chromium.launch_persistent_context(str(profile),channel=channel,headless=False,chromium_sandbox=True,viewport={'width':1280,'height':850});break
                    except Exception:continue
                if context is None:context=p.chromium.launch_persistent_context(str(profile),headless=False,chromium_sandbox=False,viewport={'width':1280,'height':850})
                page=context.pages[0] if context.pages else context.new_page()
                page.goto('https://www.tiktok.com/tiktokstudio/upload',wait_until='domcontentloaded',timeout=60000)
                self.notify('TikTok Studio đã mở. Đăng nhập bằng cửa sổ trình duyệt, rồi chọn video trong Thư viện.')
                while not self.stop.is_set() and context.pages:
                    if page.is_closed():page=context.pages[-1]
                    try:cmd,arg=self.commands.get_nowait()
                    except queue.Empty:page.wait_for_timeout(250);continue
                    if cmd=='open':page.bring_to_front();continue
                    video,caption=arg;uid=None
                    try:
                        # Isolate each review in a separate tab so another selected video cannot overwrite it.
                        page=context.new_page();page.goto('https://www.tiktok.com/tiktokstudio/upload',wait_until='domcontentloaded',timeout=60000)
                        file_input=page.locator('input[type="file"]')
                        file_input.first.wait_for(state='attached',timeout=20000)
                        uid=self.store.new_upload(video['id'],'browser:'+self.profile,'browser',caption)
                        self.store.update_upload(uid,'uploading','Đang tải vào TikTok Studio. Chưa đăng.')
                        prepare_page(page,video['path'],caption)
                        self.store.update_upload(uid,'browser_review','Đã chọn tệp và điền caption trên TikTok Studio. Chờ tải xong, kiểm tra tài khoản/quyền xem và bấm Đăng trong TikTok. Tool chưa xác nhận đã đăng.')
                        self.notify('Video đã đưa vào TikTok Studio: '+video['title']+'. Hoàn tất quyền xem và Đăng tại trình duyệt.')
                        page.bring_to_front()
                    except Exception:
                        if uid:self.store.update_upload(uid,'unknown','Chưa xác nhận tải lên hoàn tất. Kiểm tra tab TikTok đang mở trước khi gửi lại.')
                        self.notify('Chưa chuẩn bị được video trên TikTok Studio. Kiểm tra đăng nhập, CAPTCHA và tab đang mở. Bạn có thể chọn tệp thủ công: '+video['path'])
        except Exception:self.notify('Không mở được phiên TikTok Studio. Đóng hồ sơ TikTok đang dùng và thử lại; Microsoft Edge phải được cài trên máy.')
        finally:
            if context:
                try:context.close()
                except Exception:pass
