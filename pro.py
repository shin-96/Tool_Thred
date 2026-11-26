"""Threads Studio Pro desktop production workspace."""
import csv
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

import customtkinter as ctk
from PIL import Image

from threadstudio.render import ROOT
from threadstudio.source import validate_url
from threadstudio.store import Store
from threadstudio.production import ProductionQueue, video_metadata
from threadstudio.browser_publish import BrowserPublisher
from threadstudio.tiktok import TikTokAPI
from threadstudio.secrets import protect, unprotect
from threadstudio.voice_api import public_profile
from threadstudio.voice_ui import VoicePanel
from threadstudio.editing_ui import EditingPanel

STATUS={'queued':'Chờ chạy','fetching':'Lấy nội dung','rendering':'Đang dựng','ready':'Hoàn tất','failed':'Lỗi','cancelled':'Đã hủy','interrupted':'Gián đoạn','initializing':'Khởi tạo','uploading':'Đang tải','processing':'TikTok xử lý','unknown':'Cần kiểm tra','browser_review':'Chờ duyệt trên TikTok','manual_published':'Bạn xác nhận đã đăng','SEND_TO_USER_INBOX':'Đã gửi vào hộp thư','PUBLISH_COMPLETE':'Đã đăng','FAILED':'TikTok từ chối','PROCESSING_UPLOAD':'TikTok nhận tệp','PROCESSING_DOWNLOAD':'TikTok tải tệp'}
STYLES={'Thẻ giữa · mẫu 3':'center','Thẻ trên · mẫu 2':'top','Lưới xanh · mẫu 1':'grid'}
VOICES={'Việt · Hoài My':'vi-VN-HoaiMyNeural','Việt · Nam Minh':'vi-VN-NamMinhNeural','Emma · đa ngôn ngữ':'en-US-EmmaMultilingualNeural','Malay · Yasmin':'ms-MY-YasminNeural','English · Jenny':'en-US-JennyNeural'}


def table(parent,columns):
    frame=ctk.CTkFrame(parent,fg_color='transparent');frame.pack(fill='both',expand=True,padx=12,pady=8)
    tree=ttk.Treeview(frame,columns=[x[0] for x in columns],show='headings',selectmode='extended')
    for name,title,width in columns:tree.heading(name,text=title);tree.column(name,width=width,minwidth=65,stretch=True)
    y=ttk.Scrollbar(frame,orient='vertical',command=tree.yview);tree.configure(yscrollcommand=y.set)
    tree.pack(side='left',fill='both',expand=True);y.pack(side='right',fill='y');return tree


class Workspace(ctk.CTk):
    def __init__(self):
        super().__init__();ctk.set_appearance_mode('dark');ctk.set_default_color_theme('green')
        self.title('Threads Studio Pro | Production Workspace')
        self.geometry(f'{min(1420,self.winfo_screenwidth()-40)}x{min(920,self.winfo_screenheight()-70)}+10+10');self.minsize(1040,620)
        self.store=Store();self.events=queue.Queue();self.queue=ProductionQueue(self.store,self.store.get_setting('workers',2));self.browser=BrowserPublisher(self.store,lambda m:self.events.put(('message',m)))
        self.selected_videos=set();self.closing=False;self.api_busy=False;self.creator_info=None;self.creator_account=None;self.api_lock=threading.Lock();self.signatures={}
        style=ttk.Style(self);style.theme_use('clam');style.configure('Treeview',background='#192422',foreground='#dfebe6',fieldbackground='#192422',rowheight=32,borderwidth=0,font=('Segoe UI',10));style.configure('Treeview.Heading',background='#22322e',foreground='#eaf4ef',font=('Segoe UI',10,'bold'),padding=8);style.map('Treeview',background=[('selected','#246955')])
        header=ctk.CTkFrame(self,fg_color='transparent');header.pack(fill='x',padx=22,pady=(15,8))
        ctk.CTkLabel(header,text='THREADS STUDIO  PRO',font=ctk.CTkFont(size=25,weight='bold')).pack(side='left')
        self.stats=ctk.CTkLabel(header,text='Xưởng video của bạn',text_color='#93bdac');self.stats.pack(side='right')
        self.tabs=ctk.CTkTabview(self);self.tabs.pack(fill='both',expand=True,padx=18,pady=(0,12))
        for name in ['Tạo hàng loạt','Hàng đợi','Thư viện video','Chèn meme / media','API giọng đọc','TikTok','Cài đặt']:self.tabs.add(name)
        self.make_create();self.make_queue();self.make_library();self.make_tiktok();self.make_settings()
        self.voice_panel=VoicePanel(self,self.tabs.tab('API giọng đọc'));self.media_panel=EditingPanel(self,self.tabs.tab('Chèn meme / media'))
        self.status=ctk.CTkLabel(self,text='Sẵn sàng · Không tự đăng video khi tạo xong.',anchor='w',text_color='#92ac9f');self.status.pack(fill='x',padx=24,pady=(0,8))
        self.after(200,self.poll);self.protocol('WM_DELETE_WINDOW',self.close)

    def notify(self,text):self.events.put(('message',str(text)))
    def error(self,text):self.events.put(('error',str(text)))
    def background(self,fn):
        def task():
            try:fn()
            except Exception as e:self.error(e)
        threading.Thread(target=task,daemon=True).start()

    def heading(self,parent,title,detail=''):
        ctk.CTkLabel(parent,text=title,font=ctk.CTkFont(size=19,weight='bold'),anchor='w').pack(fill='x',padx=15,pady=(12,3))
        if detail:ctk.CTkLabel(parent,text=detail,text_color='#9eb8ac',wraplength=520,justify='left',anchor='w').pack(fill='x',padx=15,pady=(0,8))

    def button(self,parent,text,cmd,**kw):
        b=ctk.CTkButton(parent,text=text,command=cmd,**kw);b.pack(side='left',padx=4,pady=5);return b

    def path_input(self,parent,label,initial='',directory=False):
        row=ctk.CTkFrame(parent,fg_color='transparent');row.pack(fill='x',padx=12,pady=5)
        ctk.CTkLabel(row,text=label,width=82,anchor='w').pack(side='left');entry=ctk.CTkEntry(row);entry.pack(side='left',fill='x',expand=True,padx=5);entry.insert(0,initial)
        def choose():
            p=filedialog.askdirectory() if directory else filedialog.askopenfilename(filetypes=[('Media','*.mp4 *.mov *.mkv *.webm *.mp3 *.wav *.m4a'),('Tất cả','*.*')])
            if p:entry.delete(0,'end');entry.insert(0,p)
        self.button(row,'Chọn',choose,width=65);return entry

    def make_create(self):
        tab=self.tabs.tab('Tạo hàng loạt');tab.grid_columnconfigure(0,weight=5,uniform='create');tab.grid_columnconfigure(1,weight=4,uniform='create');tab.grid_rowconfigure(0,weight=1)
        left=ctk.CTkFrame(tab);left.grid(row=0,column=0,sticky='nsew',padx=(6,5),pady=6)
        right=ctk.CTkScrollableFrame(tab);right.grid(row=0,column=1,sticky='nsew',padx=(5,6),pady=6)
        self.heading(left,'01  Thêm nguồn video','Mỗi dòng một link Threads. Có thể trộn nhiều bài và tạo nhiều phiên bản bố cục. Dự án đã chỉnh được nhập bằng nút bên dưới.')
        self.sources=ctk.CTkTextbox(left,height=190,font=('Segoe UI',13));self.sources.pack(fill='both',expand=True,padx=15,pady=5)
        self.sources.insert('1.0','https://www.threads.com/@nguyenhoang9292/post/DgJ0tcYj8Rp')
        actions=ctk.CTkFrame(left,fg_color='transparent');actions.pack(fill='x',padx=10)
        self.button(actions,'Nhập TXT / CSV',self.import_links,width=140);self.button(actions,'Nhập dự án',self.import_projects,width=130)
        self.picked_data={};self.fetched_data={}
        self.button(actions,'Xem & chọn bình luận',self.pick_comments,width=175)
        self.button(actions,'Đăng nhập Threads',self.login_threads,width=150)
        ctk.CTkButton(left,text='Mở trình sửa & xem trước',command=self.open_editor).pack(anchor='w',padx=15,pady=5)
        self.heading(left,'Quy trình','Thêm vào hàng đợi → Bắt đầu chạy → Xem video trong Thư viện → Chọn bản muốn đưa lên TikTok.')
        self.info=ctk.CTkLabel(left,text='Nguồn mới chỉ vào hàng đợi, chưa chạy và chưa đăng.',text_color='#8fc2a8',wraplength=570,justify='left');self.info.pack(fill='x',padx=15,pady=8)
        ctk.CTkButton(left,text='THÊM LINK VÀO HÀNG ĐỢI',height=42,command=self.enqueue_links).pack(fill='x',padx=15,pady=15)
        self.heading(right,'02  Mẫu xuất cho lô này')
        self.preset=ctk.CTkOptionMenu(right,values=['Mặc định']+list(self.store.get_setting('presets',{})),command=self.load_preset);self.preset.pack(fill='x',padx=12,pady=5)
        self.style_menu=ctk.CTkOptionMenu(right,values=list(STYLES));self.style_menu.pack(fill='x',padx=12,pady=5)
        self.all_styles=ctk.CTkCheckBox(right,text='Tạo cả 3 mẫu cho mỗi nguồn');self.all_styles.pack(anchor='w',padx=12,pady=8)
        self.bg=self.path_input(right,'Video nền',str(ROOT/'assets'/'gameplay.mp4'))
        self.music=self.path_input(right,'Nhạc nền')
        self.speech=ctk.CTkSwitch(right,text='Giọng đọc trực tuyến');self.speech.select();self.speech.pack(anchor='w',padx=12,pady=8)
        self.voice_menu=ctk.CTkOptionMenu(right,values=list(VOICES));self.voice_menu.pack(fill='x',padx=12,pady=5)
        self.voice_api_menu=ctk.CTkOptionMenu(right,values=['Edge · có sẵn'],command=lambda _:self.voice_source_changed());self.voice_api_menu.pack(fill='x',padx=12,pady=5)
        self.speech_fallback=ctk.CTkCheckBox(right,text='Dự phòng giọng đa ngôn ngữ khi dịch vụ Việt lỗi');self.speech_fallback.select();self.speech_fallback.pack(anchor='w',padx=12,pady=5)
        self.funny_only=ctk.CTkCheckBox(right,text='Chỉ chọn bình luận hài, loại quảng cáo / link sản phẩm');self.funny_only.select();self.funny_only.pack(anchor='w',padx=12,pady=5)
        row=ctk.CTkFrame(right,fg_color='transparent');row.pack(fill='x',padx=12,pady=5)
        ctk.CTkLabel(row,text='Số bài / bình luận tối đa').pack(side='left');self.max_posts=ctk.CTkEntry(row,width=55);self.max_posts.insert(0,'8');self.max_posts.pack(side='right')
        row=ctk.CTkFrame(right,fg_color='transparent');row.pack(fill='x',padx=12,pady=5)
        ctk.CTkLabel(row,text='Từ/phút (khi tắt giọng đọc)').pack(side='left');self.speed=ctk.CTkEntry(row,width=55);self.speed.insert(0,'175');self.speed.pack(side='right')
        self.resolution=ctk.CTkOptionMenu(right,values=['720p','1080p']);self.resolution.pack(fill='x',padx=12,pady=5)
        self.output_dir=self.path_input(right,'Thư mục xuất',self.store.get_setting('output_dir',str(ROOT/'outputs')),True)
        ctk.CTkButton(right,text='Lưu thành preset',command=self.save_preset).pack(fill='x',padx=12,pady=8)
        ctk.CTkLabel(right,text='Nền có sẵn là vùng gameplay cắt từ mẫu. Chọn footage sạch để có góc nhìn rộng hơn. Mỗi tác vụ giữ một bản cài đặt riêng.',text_color='#9eb8ac',wraplength=450,justify='left').pack(padx=12,pady=10)

    def options(self):
        n=int(self.max_posts.get());speed=int(self.speed.get())
        if not 1<=n<=200:raise ValueError('Số bài phải từ 1 đến 200.')
        if not 60<=speed<=400:raise ValueError('Tốc độ từ 60 đến 400 từ/phút.')
        style=STYLES[self.style_menu.get()]
        if (style!='grid' or self.all_styles.get()) and not Path(self.bg.get()).is_file():raise ValueError('Chọn video nền có thật.')
        if self.music.get() and not Path(self.music.get()).is_file():raise ValueError('Không tìm thấy tệp nhạc.')
        output=Path(self.output_dir.get()).resolve();output.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(output).free<512*1024**2:raise ValueError('Ổ đĩa còn dưới 512 MB. Chọn ổ còn trống trước khi dựng.')
        api=self.selected_voice_api(self.voice_api_menu.get())
        edits=json.loads(json.dumps(self.media_panel.items)) if self.media_panel.use_batch.get() else []
        return dict(style=style,background=self.bg.get(),music=self.music.get(),speech=bool(self.speech.get()),voice=VOICES[self.voice_menu.get()],max_posts=n,speed=speed,resolution=1080 if self.resolution.get()=='1080p' else 720,speech_fallback=bool(self.speech_fallback.get()),voice_api=api,edits=edits,funny_only=bool(self.funny_only.get()))

    def refresh_voice_choices(self):
        profiles=self.store.get_setting('voice_apis',{});self.api_voice_labels={'API · '+p['name']+' · '+pid[:6]:pid for pid,p in profiles.items()}
        old=self.voice_api_menu.get();values=['Edge · có sẵn']+list(self.api_voice_labels);self.voice_api_menu.configure(values=values)
        self.voice_api_menu.set(old if old in values else values[0]);self.voice_source_changed()

    def voice_source_changed(self):
        api=self.voice_api_menu.get()!='Edge · có sẵn';self.voice_menu.configure(state='disabled' if api else 'normal');self.speech_fallback.configure(state='disabled' if api else 'normal')

    def selected_voice_api(self,label):
        if label=='Edge · có sẵn':return None
        pid=self.api_voice_labels.get(label);p=self.store.get_setting('voice_apis',{}).get(pid)
        if not p:raise ValueError('Cấu hình giọng API không còn tồn tại; hãy chọn lại.')
        return public_profile(p)

    def enqueue(self,items):
        options=self.options();styles=['center','top','grid'] if self.all_styles.get() else [options['style']]
        count=0
        for title,source,data in items:
            for style in styles:
                opts=dict(options,style=style)
                if data is not None:opts['funny_only']=False  # hand-picked comments are used exactly as chosen
                self.store.add_job(title+'_'+style,source,opts,data,self.output_dir.get());count+=1
        self.store.setting('output_dir',self.output_dir.get());self.info.configure(text=f'Đã thêm {count} video vào hàng đợi. Bấm Bắt đầu chạy khi sẵn sàng.');self.tabs.set('Hàng đợi');self.refresh()

    def login_threads(self):
        self.info.configure(text='Đang mở Chrome bằng hồ sơ riêng của app… Đăng nhập Threads trong cửa sổ đó rồi đóng cửa sổ lại là xong, app sẽ nhớ đăng nhập cho các lần lấy bài sau.')
        def task():
            from threadstudio.source import open_login_browser
            open_login_browser(lambda m:self.events.put(('message',m)))
            self.events.put(('message','Đã đóng trình duyệt đăng nhập. Giờ bấm "Xem & chọn bình luận" hoặc thêm link vào hàng đợi như bình thường.'))
        self.background(task)

    def pick_comments(self):
        try:
            links=[validate_url(x.strip()) for x in self.sources.get('1.0','end').splitlines() if x.strip()]
            if not links:raise ValueError('Nhập ít nhất một link Threads.')
        except Exception as e:messagebox.showerror('Kiểm tra nguồn',str(e),parent=self);return
        url=next((u for u in links if u not in self.picked_data),links[0])
        if url in self.fetched_data:self.open_comment_picker(url,self.fetched_data[url]);return
        self.info.configure(text='Đang lấy bình luận của bài… (mở Threads bằng Chrome, khoảng 20–40 giây)')
        def task():
            from threadstudio.source import fetch_thread
            data=fetch_thread(url,lambda m:None,limit=60)
            self.fetched_data[url]=data;self.events.put(('comments',(url,data)))
        self.background(task)

    def open_comment_picker(self,url,data):
        from threadstudio.comment_filter import auto_pick,is_ad,parse_likes
        posts=data.get('posts',[]);replies=posts[1:]
        win=ctk.CTkToplevel(self);win.title('Chọn bình luận vào video');win.geometry('780x580');win.transient(self)
        ctk.CTkLabel(win,text='Bài gốc · @'+(posts[0]['username'] if posts else '?'),font=ctk.CTkFont(size=15,weight='bold'),anchor='w').pack(fill='x',padx=14,pady=(12,2))
        ctk.CTkLabel(win,text=(posts[0]['text'][:220] if posts else ''),wraplength=740,justify='left',anchor='w',text_color='#9eb8ac').pack(fill='x',padx=14)
        bar=ctk.CTkFrame(win,fg_color='transparent');bar.pack(fill='x',padx=10,pady=6)
        counter=ctk.CTkLabel(bar,text='');counter.pack(side='right',padx=8)
        frame=ctk.CTkScrollableFrame(win);frame.pack(fill='both',expand=True,padx=10,pady=4)
        try:n=int(self.max_posts.get())
        except Exception:n=8
        preselect=auto_pick(posts,n) if self.funny_only.get() else {id(p) for p in replies}
        variables=[]
        def recount():counter.configure(text=f'Đã chọn {sum(1 for v in variables if v.get())} / {len(replies)} bình luận')
        for p in replies:
            var=tk.BooleanVar(value=id(p) in preselect);variables.append(var)
            row=ctk.CTkFrame(frame,fg_color='transparent');row.pack(fill='x',pady=2)
            ctk.CTkCheckBox(row,text='',variable=var,width=24,command=recount).pack(side='left')
            tag=' · ⚠ nghi quảng cáo' if is_ad(p.get('text','')) else ''
            if p.get('media'):tag+=' · có video đính kèm' if p['media'].get('type')=='video' else ' · có ảnh đính kèm'
            likes=parse_likes(p);like_txt=f' · {int(likes)} like' if likes else ''
            kw={'text_color':'#e88f8f'} if tag else {}
            ctk.CTkLabel(row,text=f"@{p['username']}{like_txt}{tag} — "+' '.join(p.get('text','').split())[:130],wraplength=660,justify='left',anchor='w',**kw).pack(side='left',fill='x',expand=True)
        def set_auto():
            chosen=auto_pick(posts,int(self.max_posts.get()))
            for p,var in zip(replies,variables):var.set(id(p) in chosen)
            recount()
        def set_all(value):
            for var in variables:var.set(value)
            recount()
        self.button(bar,'Tự động chọn câu hài',set_auto,width=165);self.button(bar,'Chọn tất cả',lambda:set_all(True),width=105);self.button(bar,'Bỏ chọn hết',lambda:set_all(False),width=105)
        def apply():
            chosen=[p for p,var in zip(replies,variables) if var.get()]
            self.picked_data[url]={'url':url,'posts':[posts[0]]+chosen}
            self.max_posts.delete(0,'end');self.max_posts.insert(0,str(len(chosen)+1))
            self.info.configure(text=f'Đã chốt {len(chosen)} bình luận cho bài …{url.rstrip("/").split("/")[-1]}. Bấm THÊM LINK VÀO HÀNG ĐỢI để tạo video đúng các câu này.')
            win.destroy()
        foot=ctk.CTkFrame(win,fg_color='transparent');foot.pack(fill='x',padx=10,pady=8)
        ctk.CTkButton(foot,text='DÙNG CÁC CÂU ĐÃ CHỌN',command=apply).pack(side='right')
        ctk.CTkButton(foot,text='Để tự động hoàn toàn',command=lambda:(self.picked_data.pop(url,None),win.destroy())).pack(side='right',padx=8)
        recount()
        try:win.grab_set()
        except Exception:pass

    def enqueue_links(self):
        try:
            links=list(dict.fromkeys(x.strip() for x in self.sources.get('1.0','end').splitlines() if x.strip()))
            if not links:raise ValueError('Nhập ít nhất một link Threads.')
            items=[]
            for url in links:
                url=validate_url(url);items.append((url.rstrip('/').split('/')[-1],url,self.picked_data.get(url)))
            self.enqueue(items)
        except Exception as e:messagebox.showerror('Kiểm tra nguồn',str(e),parent=self)

    def import_links(self):
        p=filedialog.askopenfilename(filetypes=[('Danh sách link','*.txt *.csv')])
        if not p:return
        try:
            text=Path(p).read_text(encoding='utf-8-sig')
            if p.lower().endswith('.csv'):links=[cell.strip() for row in csv.reader(text.splitlines()) for cell in row if cell.strip().startswith('https://')]
            else:links=[line.strip() for line in text.splitlines() if line.strip()]
            self.sources.delete('1.0','end');self.sources.insert('1.0','\n'.join(links));self.info.configure(text=f'Đã nhập {len(links)} dòng; chưa thêm vào hàng đợi.')
        except Exception as e:messagebox.showerror('Không đọc được danh sách',str(e))

    def import_projects(self):
        paths=filedialog.askopenfilenames(filetypes=[('Dự án Threads','*.json')])
        if not paths:return
        try:
            items=[]
            for path in paths:
                data=json.loads(Path(path).read_text(encoding='utf8'))
                if not isinstance(data,dict) or not isinstance(data.get('posts'),list) or not data['posts']:raise ValueError('Dự án cần có bài viết: '+Path(path).name)
                for post in data['posts']:
                    if not isinstance(post.get('text'),str) or not post['text'].strip() or not isinstance(post.get('username'),str):raise ValueError('Bài cần tên và nội dung: '+Path(path).name)
                items.append((Path(path).stem,str(Path(path).resolve()),data))
            self.enqueue(items)
        except Exception as e:messagebox.showerror('Không nhập được dự án',str(e))

    def open_editor(self):
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        cmd=[sys.executable,'--editor'] if getattr(sys,'frozen',False) else [sys.executable,str(ROOT/'app.py')]
        subprocess.Popen(cmd,cwd=str(ROOT),creationflags=flags)

    def save_preset(self):
        try:
            options=self.options();name=ctk.CTkInputDialog(text='Tên mẫu cài đặt:',title='Lưu preset').get_input()
            if not name:return
            presets=self.store.get_setting('presets',{});presets[name]=options;self.store.setting('presets',presets);self.preset.configure(values=['Mặc định']+list(presets));self.preset.set(name)
        except Exception as e:messagebox.showerror('Không lưu được preset',str(e))

    def load_preset(self,name):
        p=self.store.get_setting('presets',{}).get(name)
        if not p:return
        api=p.get('voice_api');label=next((label for label,pid in self.api_voice_labels.items() if api and pid==api['id']),'Edge · có sẵn')
        if api and label=='Edge · có sẵn':messagebox.showerror('Thiếu giọng API','Cấu hình API của preset đã bị gỡ. Thêm lại hoặc chọn preset khác.');return
        self.voice_api_menu.set(label);self.voice_source_changed()
        self.style_menu.set(next(k for k,v in STYLES.items() if v==p['style']));self.voice_menu.set(next(k for k,v in VOICES.items() if v==p['voice']))
        for entry,key in [(self.bg,'background'),(self.music,'music'),(self.max_posts,'max_posts'),(self.speed,'speed')]:entry.delete(0,'end');entry.insert(0,str(p[key]))
        self.speech.select() if p['speech'] else self.speech.deselect();self.resolution.set(str(p['resolution'])+'p')
        self.funny_only.select() if p.get('funny_only') else self.funny_only.deselect()
        self.speech_fallback.select() if p.get('speech_fallback',True) else self.speech_fallback.deselect()
        self.media_panel.items=json.loads(json.dumps(p.get('edits',[])));self.media_panel.selected=None;self.media_panel.refresh()
        self.media_panel.use_batch.select() if p.get('edits') else self.media_panel.use_batch.deselect()

    def make_queue(self):
        tab=self.tabs.tab('Hàng đợi');self.heading(tab,'Hàng đợi sản xuất','Lưu tiến trình trên máy. Tác vụ gián đoạn cần chọn Thử lại; ứng dụng không tự đăng video sau khi dựng.')
        row=ctk.CTkFrame(tab,fg_color='transparent');row.pack(fill='x',padx=10)
        self.button(row,'▶ Bắt đầu chạy',lambda:(self.queue.start(),self.refresh()),width=160);self.button(row,'Tạm dừng nhận việc',lambda:(self.queue.pause(),self.refresh()),width=175)
        self.button(row,'Hủy mục chọn',self.cancel_jobs,width=120);self.button(row,'Thử lại mục lỗi',self.retry_jobs,width=130);self.button(row,'Sửa tác vụ',self.edit_job,width=115);self.button(row,'Mở thư mục',self.open_job_folder,width=120)
        self.queue_label=ctk.CTkLabel(tab,text='',anchor='w');self.queue_label.pack(fill='x',padx=15)
        self.job_tree=table(tab,[('title','Video',230),('status','Trạng thái',120),('progress','Tiến độ',80),('message','Thông tin',480)])
        self.job_tree.bind('<<TreeviewSelect>>',lambda _:self.show_job_logs())
        self.job_logs=ctk.CTkTextbox(tab,height=100,font=('Consolas',11));self.job_logs.pack(fill='x',padx=12,pady=(0,12))

    def cancel_jobs(self):
        for jid in self.job_tree.selection():self.queue.cancel(jid)
        self.refresh()
    def retry_jobs(self):
        for jid in self.job_tree.selection():self.store.retry(jid)
        self.refresh()
    def edit_job(self):
        selected=self.job_tree.selection()
        if len(selected)!=1:messagebox.showinfo('Chọn tác vụ','Chọn một tác vụ chờ, lỗi, hủy hoặc gián đoạn.');return
        job=self.store.job(selected[0]);allowed={'queued','failed','cancelled','interrupted'}
        if job['status'] not in allowed:messagebox.showinfo('Tác vụ đang dùng','Chỉ sửa tác vụ chưa chạy hoặc cần thử lại.');return
        self.queue.pause();options=json.loads(job['options'])
        if options.get('operation')=='edit':
            self.media_panel.items=options['edits'];self.media_panel.source={'path':job['source'],'title':job['title'],'caption':options.get('caption','')};self.media_panel.selected=None;self.media_panel.refresh();self.tabs.set('Chèn meme / media');return
        win=ctk.CTkToplevel(self);win.title('Sửa tác vụ · '+job['title']);win.geometry('570x480');win.transient(self);win.grab_set()
        self.heading(win,'Cài đặt cho video này','Sau khi lưu, chọn Thử lại nếu tác vụ đang lỗi, rồi Bắt đầu chạy.')
        speech=ctk.CTkSwitch(win,text='Dùng giọng đọc');speech.pack(anchor='w',padx=15,pady=8)
        if options.get('speech'):speech.select()
        voice=ctk.CTkOptionMenu(win,values=list(VOICES));voice.set(next((k for k,v in VOICES.items() if v==options.get('voice')),list(VOICES)[0]));voice.pack(fill='x',padx=15,pady=8)
        api_menu=ctk.CTkOptionMenu(win,values=['Edge · có sẵn']+list(self.api_voice_labels));api_menu.pack(fill='x',padx=15,pady=8)
        selected_api=options.get('voice_api');api_menu.set(next((label for label,pid in self.api_voice_labels.items() if selected_api and pid==selected_api['id']),'Edge · có sẵn'))
        style=ctk.CTkOptionMenu(win,values=list(STYLES));style.set(next(k for k,v in STYLES.items() if v==options['style']));style.pack(fill='x',padx=15,pady=8)
        count=ctk.CTkEntry(win);count.insert(0,str(options['max_posts']));count.pack(fill='x',padx=15,pady=8)
        def save():
            try:
                n=int(count.get())
                if not 1<=n<=200:raise ValueError('Số bài từ 1 đến 200.')
                options.update(speech=bool(speech.get()),voice=VOICES[voice.get()],style=STYLES[style.get()],max_posts=n,voice_api=self.selected_voice_api(api_menu.get()))
                with self.store.connect() as c:
                    updated=c.execute("UPDATE jobs SET options=? WHERE id=? AND status IN ('queued','failed','cancelled','interrupted')",(json.dumps(options),job['id'])).rowcount
                if not updated:raise ValueError('Tác vụ đã thay đổi trạng thái, không lưu được.')
                win.destroy();self.notify('Đã lưu cài đặt tác vụ. Hàng đợi đang tạm dừng nhận việc.')
            except Exception as e:messagebox.showerror('Không lưu được',str(e),parent=win)
        ctk.CTkButton(win,text='Lưu thay đổi',command=save).pack(fill='x',padx=15,pady=12)
    def open_job_folder(self):
        sel=self.job_tree.selection()
        if sel:os.startfile(str(Path(self.store.job(sel[0])['output']).parent))
    def show_job_logs(self):
        selected=self.job_tree.selection()
        if not selected:return
        rows=self.store.rows('SELECT message FROM logs WHERE job_id=? ORDER BY id DESC LIMIT 25',(selected[0],))
        self.job_logs.delete('1.0','end');self.job_logs.insert('1.0','\n'.join(r['message'] for r in reversed(rows)))

    def make_library(self):
        tab=self.tabs.tab('Thư viện video');self.heading(tab,'Chọn video để xem, chỉnh caption và đưa lên TikTok','Ctrl / Shift để chọn nhiều video. Chỉ các mục được chọn mới đi vào bước đăng.')
        row=ctk.CTkFrame(tab,fg_color='transparent');row.pack(fill='x',padx=10)
        self.search=ctk.CTkEntry(row,placeholder_text='Tìm tên video…',width=230);self.search.pack(side='left',padx=4);self.search.bind('<KeyRelease>',lambda _:self.refresh())
        self.button(row,'Nhập MP4 có sẵn',self.import_videos,width=150);self.button(row,'Xem video',self.play_video,width=110);self.button(row,'Sửa caption',self.edit_caption,width=120);self.button(row,'Chọn để đăng TikTok',self.go_tiktok,width=180)
        body=ctk.CTkFrame(tab,fg_color='transparent');body.pack(fill='both',expand=True)
        self.library_left=ctk.CTkFrame(body);self.library_left.pack(side='left',fill='both',expand=True,padx=(6,5),pady=6)
        self.library_tree=table(self.library_left,[('title','Video',250),('duration','Độ dài',80),('size','Khung hình',110),('status','TikTok',165)])
        self.library_tree.bind('<<TreeviewSelect>>',self.library_select)
        preview=ctk.CTkFrame(body,width=280);preview.pack(side='right',fill='y',padx=(5,6),pady=6);preview.pack_propagate(False)
        self.video_preview=ctk.CTkLabel(preview,text='Chọn một video',height=300);self.video_preview.pack(fill='x',padx=10,pady=10)
        self.video_details=ctk.CTkTextbox(preview,height=160);self.video_details.pack(fill='both',expand=True,padx=10,pady=(0,10))
        self.library_selection=ctk.CTkLabel(tab,text='Chưa chọn video',anchor='w');self.library_selection.pack(fill='x',padx=15,pady=5)

    def import_videos(self):
        paths=filedialog.askopenfilenames(filetypes=[('Video','*.mp4 *.mov *.mkv *.webm')])
        if not paths:return
        def task():
            failures=[]
            for p in paths:
                try:self.store.add_video(p,Path(p).stem,video_metadata(p))
                except Exception as e:failures.append(Path(p).name+': '+str(e))
            self.notify(f'Đã xử lý {len(paths)} video. '+('; '.join(failures) if failures else 'Đã thêm vào thư viện.'))
        self.background(task)

    def selected_records(self):return [v for v in self.store.videos() if v['id'] in self.selected_videos]
    def library_select(self,_=None):
        self.selected_videos=set(self.library_tree.selection());records=self.selected_records();self.library_selection.configure(text=f'Đã chọn {len(records)} video')
        if records:
            v=records[0]
            if v['thumbnail'] and Path(v['thumbnail']).exists():
                im=Image.open(v['thumbnail']);im.thumbnail((245,320));self.thumbnail=ctk.CTkImage(im,size=im.size);self.video_preview.configure(image=self.thumbnail,text='')
            else:self.video_preview.configure(image=None,text='Chưa có ảnh xem trước')
            self.video_details.delete('1.0','end');self.video_details.insert('1.0',v['title']+'\n\n'+v['caption']+'\n\n'+v['path'])
        self.update_selection()

    def play_video(self):
        records=self.selected_records()
        if records:
            if Path(records[0]['path']).exists():os.startfile(records[0]['path'])
            else:messagebox.showerror('Không tìm thấy tệp','Video đã bị di chuyển khỏi đường dẫn thư viện.')

    def edit_caption(self):
        records=self.selected_records()
        if len(records)!=1:messagebox.showinfo('Sửa caption','Chọn đúng một video để sửa caption riêng.');return
        v=records[0];win=ctk.CTkToplevel(self);win.title('Caption · '+v['title']);win.geometry('650x430');win.transient(self);win.grab_set()
        text=ctk.CTkTextbox(win);text.pack(fill='both',expand=True,padx=15,pady=15);text.insert('1.0',v['caption'])
        def save():
            caption=text.get('1.0','end').strip()
            if len(caption.encode('utf-16-le'))//2>2200:messagebox.showerror('Caption quá dài','Giới hạn 2200 ký tự UTF-16.',parent=win);return
            self.store.execute('UPDATE videos SET caption=? WHERE id=?',(caption,v['id']));win.destroy();self.library_select()
        ctk.CTkButton(win,text='Lưu caption',command=save).pack(pady=(0,15))

    def go_tiktok(self):
        if not self.selected_records():messagebox.showinfo('Chọn video','Chọn video trong thư viện trước.');return
        self.update_selection();self.tabs.set('TikTok')

    def make_tiktok(self):
        tab=self.tabs.tab('TikTok');self.heading(tab,'Đăng video đã chọn','Trình duyệt: tải vào TikTok Studio để duyệt và bấm Đăng. API: cần token được TikTok cấp quyền; có hộp thư nháp và đăng trực tiếp.')
        row=ctk.CTkFrame(tab);row.pack(fill='x',padx=12,pady=5)
        self.tiktok_selected=ctk.CTkLabel(row,text='Chưa chọn video trong Thư viện',anchor='w',justify='left',wraplength=1100);self.tiktok_selected.pack(fill='x',padx=12,pady=10)
        modes=ctk.CTkFrame(tab,fg_color='transparent');modes.pack(fill='x',padx=6,pady=4)
        browser=ctk.CTkFrame(modes);browser.pack(side='left',fill='both',expand=True,padx=6)
        self.heading(browser,'TikTok Studio','Đăng nhập trực tiếp trong Edge. Tool không yêu cầu mật khẩu TikTok. Chọn một video mỗi lần để kiểm tra đầy đủ trước khi đăng.')
        self.browser_profile=ctk.CTkEntry(browser,placeholder_text='Tên hồ sơ trình duyệt');self.browser_profile.insert(0,'main');self.browser_profile.pack(fill='x',padx=12,pady=4)
        actions=ctk.CTkFrame(browser,fg_color='transparent');actions.pack(fill='x',padx=8)
        self.button(actions,'Mở / đăng nhập',self.open_browser,width=145);self.button(actions,'Tải video đã chọn',self.browser_upload,width=155);self.button(actions,'Đóng phiên',self.browser.close,width=105)
        api=ctk.CTkFrame(modes);api.pack(side='left',fill='both',expand=True,padx=6)
        self.heading(api,'Content Posting API','Token và quyền do TikTok cấp; thêm tài khoản tại Cài đặt. Ứng dụng chưa qua duyệt có giới hạn đăng riêng tư. Hộp thư nháp cần hoàn tất trong TikTok.')
        self.account=ctk.CTkOptionMenu(api,values=list(self.store.get_setting('tiktok_accounts',{})) or ['Chưa có tài khoản']);self.account.pack(fill='x',padx=12,pady=4)
        self.api_mode=ctk.CTkOptionMenu(api,values=['Gửi vào hộp thư TikTok','Đăng trực tiếp'],command=lambda _:self.reset_creator());self.api_mode.pack(fill='x',padx=12,pady=4)
        self.privacy=ctk.CTkOptionMenu(api,values=['Chưa chọn quyền xem']);self.privacy.pack(fill='x',padx=12,pady=4)
        self.creator_label=ctk.CTkLabel(api,text='Chưa kiểm tra tài khoản',anchor='w');self.creator_label.pack(fill='x',padx=12)
        actions=ctk.CTkFrame(api,fg_color='transparent');actions.pack(fill='x',padx=8)
        self.button(actions,'Kiểm tra tài khoản',self.check_creator,width=160);self.button(actions,'Gửi các video đã chọn',self.api_upload,width=185)
        options=ctk.CTkFrame(api,fg_color='transparent');options.pack(fill='x',padx=12,pady=5)
        self.aigc=ctk.CTkCheckBox(options,text='Nội dung AI');self.aigc.pack(side='left');self.allow_comments=ctk.CTkCheckBox(options,text='Cho bình luận');self.allow_comments.pack(side='left',padx=6)
        self.heading(tab,'Lịch sử TikTok','“Chờ duyệt” hoặc “TikTok xử lý” chưa có nghĩa đã đăng. Không tự gửi lại mục có kết quả chưa rõ để tránh trùng video.')
        actions=ctk.CTkFrame(tab,fg_color='transparent');actions.pack(fill='x',padx=8)
        self.button(actions,'Tra cứu mục API đã chọn',self.check_upload_status,width=220)
        self.button(actions,'Xác nhận đã đăng trên web',self.mark_browser_published,width=225)
        self.button(actions,'Cho phép gửi lại sau kiểm tra',self.release_upload,width=235)
        self.upload_tree=table(tab,[('title','Video',230),('account','Tài khoản',130),('mode','Cách gửi',100),('status','Trạng thái',160),('message','Chi tiết',400)])

    def reset_creator(self):
        self.creator_info=None;self.creator_account=None;self.privacy.configure(values=['Chưa chọn quyền xem']);self.privacy.set('Chưa chọn quyền xem');self.creator_label.configure(text='Chưa kiểm tra tài khoản')

    def update_selection(self):
        if not hasattr(self,'tiktok_selected'):return
        records=self.selected_records();self.tiktok_selected.configure(text=f'Đã chọn {len(records)} video: '+', '.join(v['title'] for v in records[:6])+('…' if len(records)>6 else ''))

    def open_browser(self):
        profile=''.join(c for c in self.browser_profile.get() if c.isalnum() or c in '-_')
        if not profile:messagebox.showerror('Tên hồ sơ','Tên chỉ gồm chữ, số, _ hoặc -.');return
        try:self.browser.open(profile)
        except Exception as e:messagebox.showerror('TikTok Studio',str(e))

    def browser_upload(self):
        records=self.selected_records()
        if len(records)!=1:messagebox.showinfo('Chọn một video','Chọn một video cho mỗi lượt TikTok Studio. API hỗ trợ gửi nhiều video đã chọn.');return
        v=records[0]
        if not messagebox.askokcancel('Đưa video lên TikTok Studio',v['title']+'\n\nCaption:\n'+v['caption'][:1000]+'\n\nVideo này sẽ được tải vào phiên TikTok đang đăng nhập. Bạn kiểm tra quyền xem và bấm Đăng trên TikTok.'):return
        try:self.browser.prepare(v,v['caption']);self.notify('Đang chuẩn bị video trong TikTok Studio…')
        except Exception as e:messagebox.showerror('TikTok Studio',str(e))

    def get_api(self,account=None):
        account=account or self.account.get();encrypted=self.store.get_setting('tiktok_accounts',{}).get(account)
        if not encrypted:raise ValueError('Chưa có tài khoản API. Thêm access token được cấp quyền tại Cài đặt.')
        return TikTokAPI(unprotect(encrypted))

    def check_creator(self):
        account=self.account.get()
        def task():self.events.put(('creator',(account,self.get_api(account).creator())))
        self.background(task)

    def api_upload(self):
        if self.api_busy:messagebox.showinfo('Đang gửi','Chờ lô hiện tại hoàn tất trước.');return
        records=self.selected_records();account=self.account.get();mode='direct' if self.api_mode.get()=='Đăng trực tiếp' else 'inbox';privacy=self.privacy.get()
        if not records:messagebox.showinfo('Chọn video','Chọn video trong Thư viện trước.');return
        try:
            self.get_api(account)
            if mode=='direct' and (self.creator_account!=account or not self.creator_info or privacy not in self.creator_info.get('privacy_level_options',[])):raise ValueError('Kiểm tra đúng tài khoản và chọn quyền xem trước khi đăng trực tiếp.')
        except Exception as e:messagebox.showerror('Chưa sẵn sàng',str(e));return
        summary='\n'.join('• '+v['title']+'\n  '+v['caption'][:180] for v in records)
        destination=(self.creator_info.get('creator_nickname','') if mode=='direct' else account)
        if not messagebox.askokcancel('Xác nhận gửi TikTok',f'Tài khoản: {destination}\nHình thức: {"Đăng trực tiếp · "+privacy if mode=="direct" else "Gửi hộp thư, chưa đăng"}\n\n{summary[:2600]}\n\nGửi đúng các video và caption này lên TikTok?'):return
        options={'aigc':bool(self.aigc.get()),'allow_comment':bool(self.allow_comments.get())};self.api_busy=True
        def task():
            try:
                api=self.get_api(account)
                for v in records:
                    uid=None;initialized=False
                    try:
                        uid=self.store.new_upload(v['id'],account,mode,v['caption'])
                        creator=api.creator() if mode=='direct' else None
                        def on_init(pid):
                            nonlocal initialized
                            initialized=True;self.store.update_upload(uid,'uploading','Đang gửi dữ liệu video.',pid)
                        api.upload(v['path'],v['caption'],mode,privacy,creator,on_init,post_options=options)
                        self.store.update_upload(uid,'processing','Đã gửi tệp. Tra cứu để biết TikTok xử lý xong hay chưa.')
                    except Exception as e:
                        if uid:self.store.update_upload(uid,'unknown' if initialized or getattr(e,'uncertain',False) else 'failed',str(e))
                        self.notify('TikTok: '+v['title']+' · '+str(e))
                    if len(records)>1:threading.Event().wait(11)
            finally:self.events.put(('api_done',None))
        self.background(task)

    def check_upload_status(self):
        ids=set(self.upload_tree.selection());records=[u for u in self.store.uploads() if u['id'] in ids]
        def task():
            for u in records:
                if not u['publish_id']:continue
                result=self.get_api(u['account']).status(u['publish_id']);self.store.update_upload(u['id'],result['status'],result.get('fail_reason',''))
            self.notify('Đã tra cứu các mục có publish_id.')
        self.background(task)

    def mark_browser_published(self):
        ids=set(self.upload_tree.selection());records=[u for u in self.store.uploads() if u['id'] in ids and u['mode']=='browser' and u['status'] in {'browser_review','unknown'}]
        if not records:return
        if messagebox.askokcancel('Xác nhận thủ công','Bạn đã kiểm tra và thấy các video này được đăng trên TikTok?\n'+ '\n'.join(u['title'] for u in records)):
            for u in records:self.store.update_upload(u['id'],'manual_published','Người dùng xác nhận trên TikTok; không phải kết quả tra cứu API.')

    def release_upload(self):
        ids=set(self.upload_tree.selection());records=[u for u in self.store.uploads() if u['id'] in ids and u['status'] in {'unknown','browser_review','failed','FAILED'}]
        if not records:return
        if messagebox.askokcancel('Cho phép gửi lại','Chỉ tiếp tục sau khi bạn đã kiểm tra TikTok và xác nhận các video này CHƯA đăng / CHƯA chờ xử lý. Điều này mở khóa gửi lại, không xóa bản đang có trên TikTok.\n\n'+'\n'.join(u['title'] for u in records)):
            for u in records:self.store.update_upload(u['id'],'cancelled','Người dùng đã kiểm tra và cho phép gửi lại.')

    def make_settings(self):
        tab=self.tabs.tab('Cài đặt');self.heading(tab,'Tài nguyên & tài khoản','Dữ liệu, lịch sử và hồ sơ riêng nằm trong thư mục data cạnh công cụ. Giữ nguyên thư mục khi chuyển máy.')
        body=ctk.CTkScrollableFrame(tab);body.pack(fill='both',expand=True,padx=12,pady=5)
        self.heading(body,'Chạy đồng thời','Chọn 1–3 tác vụ dựng. Máy ít RAM nên dùng 1; mặc định 2. Thay đổi có hiệu lực với việc nhận tác vụ mới.')
        self.workers=ctk.CTkOptionMenu(body,values=['1','2','3'],command=self.set_workers);self.workers.set(str(self.queue.workers));self.workers.pack(anchor='w',padx=15,pady=5)
        self.heading(body,'Tài khoản TikTok API','Nhập access token của tài khoản đã ủy quyền video.upload / video.publish. Token lưu bằng Windows DPAPI, không ghi vào nhật ký. Không cần token khi dùng TikTok Studio qua trình duyệt.')
        self.account_name=ctk.CTkEntry(body,placeholder_text='Tên gợi nhớ tài khoản',width=400);self.account_name.pack(anchor='w',padx=15,pady=5)
        self.token=ctk.CTkEntry(body,placeholder_text='Access token TikTok',show='•',width=600);self.token.pack(fill='x',padx=15,pady=5)
        ctk.CTkButton(body,text='Lưu / cập nhật tài khoản',command=self.save_account).pack(anchor='w',padx=15,pady=8)
        ctk.CTkButton(body,text='Gỡ token tài khoản đang chọn',command=self.remove_account,fg_color='#784c45').pack(anchor='w',padx=15,pady=4)
        self.heading(body,'Chẩn đoán & dữ liệu','Không cần cấp quyền quản trị. Nếu Threads không hiện bình luận, thử lại hoặc dùng bài gốc từ phương án dự phòng; có thể nhập nội dung đã chỉnh bằng dự án.')
        self.diagnostics=ctk.CTkLabel(body,text='',anchor='w',justify='left');self.diagnostics.pack(fill='x',padx=15,pady=5)
        row=ctk.CTkFrame(body,fg_color='transparent');row.pack(fill='x',padx=10)
        self.button(row,'Kiểm tra hệ thống',self.check_system,width=170);self.button(row,'Mở thư mục dữ liệu',lambda:os.startfile(str(ROOT/'data')),width=180);self.button(row,'Xuất báo cáo CSV',self.export_report,width=170)
        self.check_system()

    def set_workers(self,value):self.queue.workers=int(value);self.store.setting('workers',int(value))
    def save_account(self):
        try:
            name=self.account_name.get().strip();token=self.token.get().strip()
            if not name or not token:raise ValueError('Nhập tên và access token.')
            accounts=self.store.get_setting('tiktok_accounts',{});accounts[name]=protect(token);self.store.setting('tiktok_accounts',accounts)
            self.account.configure(values=list(accounts));self.account.set(name);self.token.delete(0,'end');self.reset_creator();self.notify('Đã lưu token được mã hóa bằng tài khoản Windows hiện tại.')
        except Exception as e:messagebox.showerror('Chưa lưu được tài khoản',str(e))
    def check_system(self):
        text='FFmpeg: '+('OK' if shutil.which('ffmpeg') else 'THIẾU')+'  |  ffprobe: '+('OK' if shutil.which('ffprobe') else 'THIẾU')
        text+='\nDữ liệu: '+str(self.store.path)+'\nỔ đĩa trống: '+f'{shutil.disk_usage(ROOT).free/1024**3:.1f} GB'
        self.diagnostics.configure(text=text)
    def remove_account(self):
        name=self.account.get();accounts=self.store.get_setting('tiktok_accounts',{})
        if name in accounts:
            accounts.pop(name);self.store.setting('tiktok_accounts',accounts);self.account.configure(values=list(accounts) or ['Chưa có tài khoản']);self.account.set(next(iter(accounts),'Chưa có tài khoản'));self.reset_creator();self.notify('Đã gỡ token lưu tại máy. Muốn thu hồi quyền hãy làm thêm trong TikTok.')
    def export_report(self):
        path=filedialog.asksaveasfilename(defaultextension='.csv',initialfile='production_report.csv',filetypes=[('CSV','*.csv')])
        if not path:return
        with open(path,'w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(['Video','Trạng thái','Tiến độ','Đường dẫn','Thông tin'])
            for j in self.store.jobs():w.writerow([j['title'],STATUS.get(j['status'],j['status']),round(j['progress']*100),j['output'],j['message']])
        self.notify('Đã xuất báo cáo: '+path)

    def sync_tree(self,name,tree,rows):
        signature=tuple((i,tuple(v)) for i,v in rows)
        if self.signatures.get(name)==signature:return
        self.signatures[name]=signature;selection=set(tree.selection());focus=tree.focus();pos=tree.yview()
        tree.delete(*tree.get_children())
        for key,values in rows:tree.insert('','end',iid=key,values=values)
        keep=selection&set(tree.get_children())
        if keep:tree.selection_set(list(keep))
        if focus in tree.get_children():tree.focus(focus)
        if pos:tree.yview_moveto(pos[0])

    def refresh(self):
        jobs=self.store.jobs();videos=self.store.videos();uploads=self.store.uploads();counts={s:sum(j['status']==s for j in jobs) for s in ['queued','fetching','rendering','ready','failed']}
        self.stats.configure(text=f"{len(videos)} video  ·  {counts['queued']} chờ  ·  {counts['fetching']+counts['rendering']} đang chạy  ·  {counts['failed']} lỗi")
        self.queue_label.configure(text=f"{'ĐANG NHẬN VIỆC' if self.queue.enabled else 'TẠM DỪNG NHẬN VIỆC'}  ·  Tối đa {self.queue.workers} tác vụ đồng thời")
        self.sync_tree('jobs',self.job_tree,[(j['id'],[j['title'],STATUS.get(j['status'],j['status']),str(round(j['progress']*100))+'%',j['message'][:200]]) for j in jobs])
        recent={}
        for u in reversed(uploads):recent[u['video_id']]=STATUS.get(u['status'],u['status'])
        q=self.search.get().lower().strip()
        self.sync_tree('videos',self.library_tree,[(v['id'],[v['title'],f"{int(v['duration']//60)}:{int(v['duration']%60):02}",f"{v['width']} × {v['height']}",recent.get(v['id'],'Chưa gửi')]) for v in videos if q in v['title'].lower()])
        self.selected_videos&={v['id'] for v in videos};self.update_selection()
        self.sync_tree('uploads',self.upload_tree,[(u['id'],[u['title'],u['account'],u['mode'],STATUS.get(u['status'],u['status']),u['message']]) for u in uploads])

    def poll(self):
        if self.closing:return
        try:
            while not self.events.empty():
                kind,value=self.events.get()
                if kind=='message':self.status.configure(text=str(value))
                elif kind=='error':self.status.configure(text=str(value));messagebox.showerror('Thông báo',str(value),parent=self)
                elif kind=='api_done':self.api_busy=False;self.notify('Lô gửi TikTok đã kết thúc. Xem lịch sử và tra cứu trạng thái.')
                elif kind=='creator':
                    account,creator=value
                    if account==self.account.get():
                        self.creator_info=creator;self.creator_account=account
                        self.creator_label.configure(text='@'+creator.get('creator_username','')+' · '+creator.get('creator_nickname',''))
                        values=['Chọn quyền xem']+creator.get('privacy_level_options',[]);self.privacy.configure(values=values);self.privacy.set(values[0])
                elif kind=='comments':
                    url,data=value;self.open_comment_picker(url,data)
                elif kind=='media_preview':
                    im,total=value;self.media_preview_img=ctk.CTkImage(im,size=im.size);self.media_panel.preview.configure(image=self.media_preview_img,text='');self.status.configure(text=f'Xem trước · video sau chỉnh sửa dài {total:.2f} giây. Bấm Lưu lớp media sau mỗi thay đổi thông số.')
            self.refresh()
        finally:self.after(1000,self.poll)

    def close(self):
        if self.api_busy:
            messagebox.showinfo('Đang tải TikTok','Chờ lượt gửi hoàn tất trước khi đóng để giữ trạng thái chính xác.');return
        if self.queue.active and not messagebox.askokcancel('Đóng công cụ','Các tác vụ dựng đang chạy sẽ được dừng. Khi mở lại có thể chọn Thử lại.'):return
        self.closing=True;self.queue.shutdown();self.browser.close()
        if self.browser.thread:self.browser.thread.join(2)
        self.destroy()


def main():
    if '--editor' in sys.argv:
        from app import Studio
        Studio().mainloop()
    else:
        # Prevent a second workspace from recovering jobs still running in the first one.
        import msvcrt
        lock_path=ROOT/'data'/'workspace.lock';lock_path.parent.mkdir(exist_ok=True)
        with lock_path.open('a+b') as lock:
            lock.seek(0,2)
            if lock.tell()==0:lock.write(b'0');lock.flush()
            lock.seek(0)
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:
                root=tk.Tk();root.withdraw();messagebox.showinfo('Threads Studio Pro','Công cụ đã mở. Hãy quay lại cửa sổ Threads Studio Pro hiện tại.');root.destroy();return
            try:Workspace().mainloop()
            finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)


if __name__=='__main__':main()
