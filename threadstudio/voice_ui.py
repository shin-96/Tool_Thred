import json
import os
import uuid
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from .voice_api import KINDS,DEFAULTS,BODY_DEFAULT,public_profile,save_profile,synthesize_api
from .render import ROOT


class VoicePanel:
    def __init__(self,app,tab):
        self.app=app;self.store=app.store;self.pid=None;self.testing=False
        app.heading(tab,'Kết nối API giọng đọc','Lưu nhiều cấu hình giọng. Key được bảo vệ bằng Windows; chỉ cấu hình giọng đi vào hàng đợi. Nút Nghe thử gửi đoạn mẫu đến dịch vụ đã chọn và có thể dùng hạn mức API.')
        form=ctk.CTkScrollableFrame(tab);form.pack(fill='both',expand=True,padx=12,pady=6)
        self.saved=ctk.CTkOptionMenu(form,values=['Cấu hình mới'],command=self.load);self.saved.pack(fill='x',padx=12,pady=8)
        self.kind=ctk.CTkOptionMenu(form,values=KINDS,command=self.defaults);self.kind.pack(fill='x',padx=12,pady=6)
        self.fields={}
        for key,label,default in [('name','Tên gợi nhớ','Giọng API mới'),('endpoint','Endpoint đầy đủ',''),('voice','Voice / Voice ID',''),('model','Model',''),('speed','Tốc độ (0.25–4)','1'),('key_header','Header của API key','Authorization'),('key_prefix','Tiền tố key (giữ dấu cách cuối)','Bearer ')]:
            row=ctk.CTkFrame(form,fg_color='transparent');row.pack(fill='x',padx=12,pady=3)
            ctk.CTkLabel(row,text=label,width=240,anchor='w').pack(side='left');e=ctk.CTkEntry(row);e.pack(side='left',fill='x',expand=True);e.insert(0,default);self.fields[key]=e
        row=ctk.CTkFrame(form,fg_color='transparent');row.pack(fill='x',padx=12,pady=4)
        ctk.CTkLabel(row,text='API key (để trống để giữ key đã lưu)',width=240,anchor='w').pack(side='left');self.key=ctk.CTkEntry(row,show='•');self.key.pack(side='left',fill='x',expand=True)
        app.heading(form,'HTTP JSON tùy chỉnh','Chỉ áp dụng cho HTTP JSON. Body dùng {text}, {voice}, {model}, {speed}. Chọn audio trực tiếp, base64 hoặc URL đã sẵn sàng; đường dẫn JSON ví dụ data.audio_url. Không nhập key vào body hoặc URL.')
        self.body=ctk.CTkTextbox(form,height=110,font=('Consolas',12));self.body.pack(fill='x',padx=12,pady=5);self.body.insert('1.0',json.dumps(BODY_DEFAULT,indent=2))
        row=ctk.CTkFrame(form,fg_color='transparent');row.pack(fill='x',padx=12,pady=4)
        self.response=ctk.CTkOptionMenu(row,values=['audio','base64','url']);self.response.pack(side='left',padx=(0,8));self.response_path=ctk.CTkEntry(row,placeholder_text='Đường dẫn trong JSON');self.response_path.insert(0,'audio');self.response_path.pack(side='left',fill='x',expand=True)
        app.heading(form,'Đoạn nghe thử','Dùng đoạn ngắn để kiểm tra đúng giọng trước khi tạo cả lô. API lỗi không tự chuyển sang giọng khác và không tự gửi lại yêu cầu có thể tính phí.')
        self.sample=ctk.CTkTextbox(form,height=70);self.sample.insert('1.0','Xin chào, đây là giọng đọc thử cho video Threads của tôi.');self.sample.pack(fill='x',padx=12,pady=5)
        row=ctk.CTkFrame(form,fg_color='transparent');row.pack(fill='x',padx=8,pady=8)
        app.button(row,'Lưu cấu hình',self.save,width=150);app.button(row,'Nghe thử cấu hình đã lưu',self.test,width=235);app.button(row,'Gỡ cấu hình',self.remove,width=140)
        self.defaults(KINDS[0]);self.refresh()

    def refresh(self):
        self.profiles=self.store.get_setting('voice_apis',{});self.labels={p['name']+' · '+pid[:6]:pid for pid,p in self.profiles.items()}
        self.saved.configure(values=['Cấu hình mới']+list(self.labels));self.app.refresh_voice_choices()

    def defaults(self,kind):
        for key,value in DEFAULTS[kind].items():self.fields[key].delete(0,'end');self.fields[key].insert(0,value)

    def collect(self):
        p={key:entry.get() for key,entry in self.fields.items()};p['name']=p['name'].strip();p['kind']=self.kind.get();p['body']=json.loads(self.body.get('1.0','end'));p['response']=self.response.get();p['response_path']=self.response_path.get().strip();return p

    def save(self):
        try:
            self.pid=save_profile(self.store,self.collect(),self.key.get(),self.pid);self.key.delete(0,'end');self.refresh()
            self.saved.set(next(label for label,pid in self.labels.items() if pid==self.pid));self.app.notify('Đã lưu cấu hình giọng API. Chọn cấu hình tại Tạo hàng loạt.')
        except Exception as e:messagebox.showerror('Không lưu được API',str(e),parent=self.app)

    def load(self,label):
        self.pid=self.labels.get(label);self.key.delete(0,'end')
        if not self.pid:self.fields['name'].delete(0,'end');self.fields['name'].insert(0,'Giọng API mới');self.defaults(self.kind.get());return
        p=self.profiles[self.pid];self.kind.set(p['kind'])
        for key,entry in self.fields.items():entry.delete(0,'end');entry.insert(0,str(p.get(key,'')))
        self.body.delete('1.0','end');self.body.insert('1.0',json.dumps(p.get('body',BODY_DEFAULT),ensure_ascii=False,indent=2));self.response.set(p.get('response','audio'));self.response_path.delete(0,'end');self.response_path.insert(0,p.get('response_path','audio'))

    def remove(self):
        if not self.pid:return
        profiles=self.store.get_setting('voice_apis',{});profiles.pop(self.pid,None);self.store.setting('voice_apis',profiles);self.pid=None;self.saved.set('Cấu hình mới');self.refresh();self.app.notify('Đã gỡ cấu hình API. Các tác vụ dùng cấu hình này cần chọn lại giọng.')

    def test(self):
        if self.testing:return
        if not self.pid:messagebox.showinfo('Lưu cấu hình','Lưu cấu hình trước khi nghe thử.');return
        text=self.sample.get('1.0','end').strip()
        if not text or len(text)>500:messagebox.showinfo('Đoạn nghe thử','Nhập từ 1–500 ký tự.');return
        profile=public_profile(self.store.get_setting('voice_apis',{})[self.pid]);self.testing=True
        def task():
            try:
                folder=ROOT/'data'/'voice_tests';folder.mkdir(exist_ok=True);path=folder/(uuid.uuid4().hex+'.mp3')
                synthesize_api(text,profile,path,log=self.app.notify,store=self.store);os.startfile(path);self.app.notify('Đã tạo âm thanh thử. Trình phát Windows đang mở.')
            finally:self.testing=False
        self.app.background(task)
