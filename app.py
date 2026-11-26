import json
import os
import queue
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk

import customtkinter as ctk
from PIL import Image

from threadstudio.source import fetch_thread, save_project
from threadstudio.render import ROOT, pages, card, composite, render, Cancelled

ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('green')
STYLES={'Thẻ giữa · mẫu 3':'center','Thẻ trên · mẫu 2':'top','Lưới xanh · mẫu 1':'grid'}
VOICES={'Malay · Yasmin':'ms-MY-YasminNeural','Việt · Hoài My':'vi-VN-HoaiMyNeural','Việt · Nam Minh':'vi-VN-NamMinhNeural','English · Jenny':'en-US-JennyNeural'}


class Studio(ctk.CTk):
    def __init__(self):
        super().__init__()
        height=min(880,self.winfo_screenheight()-65);width=min(1240,self.winfo_screenwidth()-40)
        self.title('Threads Studio | Video Editor'); self.geometry(f'{width}x{height}+10+10');self.minsize(1000,600)
        self.preview_height=min(432,max(240,height-320))
        self.events=queue.Queue();self.cancel=threading.Event();self.busy=False;self.last_output=None;self.preview_index=0
        self.grid_columnconfigure(0,weight=1);self.grid_columnconfigure(1,weight=1);self.grid_rowconfigure(1,weight=1)
        head=ctk.CTkFrame(self,fg_color='transparent');head.grid(row=0,column=0,columnspan=2,sticky='ew',padx=25,pady=15)
        ctk.CTkLabel(head,text='THREADS STUDIO',font=ctk.CTkFont(size=26,weight='bold')).pack(anchor='w')
        ctk.CTkLabel(head,text='Biến bài viết & bình luận thành video dọc 9:16',text_color='#96b0aa').pack(anchor='w')
        left=ctk.CTkScrollableFrame(self,width=590);left.grid(row=1,column=0,sticky='nsew',padx=(20,10),pady=(0,20))
        right=ctk.CTkFrame(self);right.grid(row=1,column=1,sticky='nsew',padx=(0,20),pady=(0,20))
        ctk.CTkLabel(left,text='01  NỘI DUNG THREADS',font=ctk.CTkFont(size=17,weight='bold')).pack(anchor='w',padx=15,pady=(15,8))
        self.url=ctk.CTkEntry(left,placeholder_text='https://www.threads.com/@.../post/...');self.url.pack(fill='x',padx=15)
        self.url.insert(0,'https://www.threads.com/@aisyahhhh.hani/post/Df8vzcVCZ9L')
        row=ctk.CTkFrame(left,fg_color='transparent');row.pack(fill='x',padx=15,pady=10)
        self.fetch_button=ctk.CTkButton(row,text='Lấy bài & bình luận',command=self.fetch);self.fetch_button.pack(side='left',padx=(0,8))
        ctk.CTkButton(row,text='Mở dự án',width=100,command=self.load).pack(side='left',padx=(0,8))
        ctk.CTkButton(row,text='Lưu',width=70,command=self.save).pack(side='left')
        ctk.CTkButton(left,text='Sửa, thêm & sắp xếp bình luận',command=self.edit_posts).pack(anchor='w',padx=15,pady=3)
        self.editor=ctk.CTkTextbox(left,height=180,font=('Arial',13));self.editor.pack(fill='x',padx=15,pady=8)
        self.set_data({'posts':[{'username':'ten_cua_ban','text':'Nội dung bài viết…','date':'','stats':[]}]})
        ctk.CTkLabel(left,text='02  PHONG CÁCH & ÂM THANH',font=ctk.CTkFont(size=17,weight='bold')).pack(anchor='w',padx=15,pady=(15,8))
        self.style=ctk.CTkOptionMenu(left,values=list(STYLES),command=lambda _:self.preview());self.style.pack(fill='x',padx=15,pady=5)
        self.bg=self.file_row(left,'Video nền', [('Video','*.mp4 *.mov *.mkv *.webm')],str(ROOT/'assets'/'gameplay.mp4'))
        self.music=self.file_row(left,'Nhạc nền', [('Audio','*.mp3 *.wav *.m4a *.aac')])
        self.speech=ctk.CTkSwitch(left,text='Giọng đọc tự động (cần Internet)');self.speech.select();self.speech.pack(anchor='w',padx=15,pady=8)
        self.voice=ctk.CTkOptionMenu(left,values=list(VOICES));self.voice.pack(fill='x',padx=15,pady=5)
        options=ctk.CTkFrame(left,fg_color='transparent');options.pack(fill='x',padx=15,pady=8)
        ctk.CTkLabel(options,text='Số bài tối đa').pack(side='left');self.count=ctk.CTkEntry(options,width=55);self.count.insert(0,'12');self.count.pack(side='left',padx=6)
        ctk.CTkLabel(options,text='Từ/phút khi tắt đọc').pack(side='left');self.speed=ctk.CTkEntry(options,width=55);self.speed.insert(0,'175');self.speed.pack(side='left',padx=6)
        self.resolution=ctk.CTkOptionMenu(left,values=['720p · 720 × 1280','1080p · 1080 × 1920']);self.resolution.pack(fill='x',padx=15,pady=5)
        ctk.CTkLabel(left,text='Nền có sẵn: vùng gameplay sạch được cắt từ video mẫu 2.\nChọn footage gốc của bạn để có góc nhìn rộng và sắc nét hơn.\nChỉ lấy các bình luận công khai Threads cho phép xem.',justify='left',text_color='#aebcb7',wraplength=540).pack(anchor='w',padx=15,pady=10)
        ctk.CTkLabel(right,text='XEM TRƯỚC BỐ CỤC',font=ctk.CTkFont(size=16,weight='bold')).pack(pady=(12,6))
        self.preview_label=ctk.CTkLabel(right,text='');self.preview_label.pack()
        buttons=ctk.CTkFrame(right,fg_color='transparent');buttons.pack(pady=8)
        ctk.CTkButton(buttons,text='◀',width=44,command=lambda:self.preview(-1)).pack(side='left',padx=4)
        ctk.CTkButton(buttons,text='Cập nhật xem trước',command=self.preview).pack(side='left',padx=4)
        ctk.CTkButton(buttons,text='▶',width=44,command=lambda:self.preview(1)).pack(side='left',padx=4)
        self.progress=ctk.CTkProgressBar(right);self.progress.pack(fill='x',padx=20,pady=6);self.progress.set(0)
        actions=ctk.CTkFrame(right,fg_color='transparent');actions.pack(fill='x',padx=20,pady=8)
        self.export_button=ctk.CTkButton(actions,text='XUẤT VIDEO MP4',command=self.export);self.export_button.pack(side='left',fill='x',expand=True,padx=(0,8))
        ctk.CTkButton(actions,text='Hủy',width=65,fg_color='#69433d',command=self.cancel.set).pack(side='left',padx=(0,8))
        ctk.CTkButton(actions,text='Mở video',width=90,command=self.open_output).pack(side='left')
        self.logbox=ctk.CTkTextbox(right,height=75,font=('Consolas',11));self.logbox.pack(fill='both',expand=True,padx=20,pady=(0,15))
        self.after(150,self.poll);self.after(300,self.preview)
        self.protocol('WM_DELETE_WINDOW',self.close)

    def file_row(self,parent,label,types,default=''):
        r=ctk.CTkFrame(parent,fg_color='transparent');r.pack(fill='x',padx=15,pady=5)
        ctk.CTkLabel(r,text=label,width=72,anchor='w').pack(side='left')
        e=ctk.CTkEntry(r);e.pack(side='left',fill='x',expand=True,padx=6);e.insert(0,default)
        def choose():
            p=filedialog.askopenfilename(filetypes=types)
            if p:e.delete(0,'end');e.insert(0,p)
        ctk.CTkButton(r,text='Chọn',width=60,command=choose).pack(side='left');return e

    def data(self):
        data=json.loads(json.dumps(self.project))
        if not isinstance(data,dict) or not isinstance(data.get('posts'),list) or not data['posts']:raise ValueError('JSON cần có danh sách posts không rỗng.')
        for p in data['posts']:
            if not isinstance(p,dict) or not isinstance(p.get('text'),str) or not p['text'].strip() or not isinstance(p.get('username'),str):raise ValueError('Mỗi bài cần username và text dạng chữ, không để trống.')
        return data

    def log(self,text):self.events.put(('log',str(text)))
    def start(self,fn):
        if self.busy:return
        self.busy=True;self.cancel.clear();self.fetch_button.configure(state='disabled');self.export_button.configure(state='disabled')
        def task():
            try:fn()
            except Exception as e:self.events.put(('error',str(e)))
            finally:self.events.put(('done',None))
        threading.Thread(target=task,daemon=True).start()

    def fetch(self):
        url=self.url.get()
        def task():self.events.put(('data',fetch_thread(url,self.log)))
        self.start(task)

    def load(self):
        if self.busy:return
        p=filedialog.askopenfilename(filetypes=[('Dự án JSON','*.json')])
        if p:
            try:self.set_data(json.loads(Path(p).read_text(encoding='utf8')));self.data();self.preview()
            except Exception as e:messagebox.showerror('Dự án không hợp lệ',str(e))

    def set_data(self,d):
        self.project=d
        self.editor.configure(state='normal');self.editor.delete('1.0','end')
        for i,p in enumerate(d.get('posts',[])):
            self.editor.insert('end',f"{'BÀI GỐC' if i==0 else 'BÌNH LUẬN '+str(i)}  ·  @{p.get('username','')}\n{p.get('text','')}\n\n")
        self.editor.configure(state='disabled')

    def edit_posts(self):
        if self.busy:return
        d=self.data();posts=d['posts'];win=ctk.CTkToplevel(self);win.title('Sửa bài viết & bình luận');win.geometry('880x570');win.transient(self);win.grab_set()
        win.grid_columnconfigure(1,weight=1);win.grid_rowconfigure(0,weight=1)
        lb=tk.Listbox(win,bg='#242b29',fg='white',selectbackground='#26785d',width=27,exportselection=False,font=('Arial',12));lb.grid(row=0,column=0,sticky='nsew',padx=12,pady=12)
        pane=ctk.CTkFrame(win);pane.grid(row=0,column=1,sticky='nsew',padx=(0,12),pady=12)
        ctk.CTkLabel(pane,text='Tên tài khoản').pack(anchor='w',padx=12,pady=(12,3));name=ctk.CTkEntry(pane);name.pack(fill='x',padx=12)
        ctk.CTkLabel(pane,text='Nội dung (sẽ tự chia trang khi dài)').pack(anchor='w',padx=12,pady=(12,3));body=ctk.CTkTextbox(pane,height=300);body.pack(fill='both',expand=True,padx=12,pady=(0,8))
        selected=[0]
        def show(index):
            selected[0]=index;name.delete(0,'end');name.insert(0,posts[index]['username']);body.delete('1.0','end');body.insert('1.0',posts[index]['text'])
        def refresh(index=0):
            lb.delete(0,'end')
            for i,p in enumerate(posts):lb.insert('end',f'{i+1}. @{p["username"]}')
            lb.selection_set(index);show(index)
        def apply():
            if not name.get().strip() or not body.get('1.0','end').strip():raise ValueError('Tên và nội dung không được để trống.')
            posts[selected[0]]['username']=name.get().strip().lstrip('@');posts[selected[0]]['text']=body.get('1.0','end').strip()
        def save_current():
            try:apply();refresh(selected[0])
            except Exception as e:messagebox.showerror('Kiểm tra nội dung',str(e),parent=win)
        def choose(_):
            if lb.curselection():show(lb.curselection()[0])
        lb.bind('<<ListboxSelect>>',choose)
        def add():posts.append({'username':'user','text':'Bình luận mới','date':'','stats':[]});refresh(len(posts)-1)
        def delete():
            if len(posts)==1:return
            posts.pop(selected[0]);refresh(min(selected[0],len(posts)-1))
        def move(delta):
            i=selected[0];j=i+delta
            if 0<=j<len(posts):posts[i],posts[j]=posts[j],posts[i];refresh(j)
        actions=ctk.CTkFrame(win,fg_color='transparent');actions.grid(row=1,column=0,columnspan=2,padx=12,pady=(0,12),sticky='ew')
        for title,cmd in [('Lưu đoạn đang sửa',save_current),('Thêm',add),('Xóa',delete),('↑',lambda:move(-1)),('↓',lambda:move(1))]:ctk.CTkButton(actions,text=title,width=85,command=cmd).pack(side='left',padx=3)
        def done():
            try:apply();self.set_data(d);self.preview_index=0;self.preview();win.destroy()
            except Exception as e:messagebox.showerror('Kiểm tra nội dung',str(e),parent=win)
        ctk.CTkButton(actions,text='Hoàn tất',width=100,command=done).pack(side='right');refresh()
    def save(self):
        try:
            d=self.data();p=filedialog.asksaveasfilename(defaultextension='.json',filetypes=[('Dự án','*.json')])
            if p:save_project(d,p)
        except Exception as e:messagebox.showerror('Không lưu được',str(e))

    def preview(self,delta=0):
        try:
            data=self.data();style=STYLES[self.style.get()];scenes=[]
            for pi,p in enumerate(data['posts']):
                chunks=pages(p,9 if style=='grid' else 18,22 if style=='grid' else 25)
                for ci,lines in enumerate(chunks):scenes.append((pi,p,ci,len(chunks),lines))
            self.preview_index=(self.preview_index+(delta if isinstance(delta,int) else 0))%len(scenes)
            pi,p,ci,n,lines=scenes[self.preview_index]
            cache=ROOT/'assets'/'avatars';cache.mkdir(exist_ok=True)
            c=card(p,lines,ci,n,cache,22 if style=='grid' else 25,style!='center')
            pin=None
            if style=='grid' and pi>0:
                pp=pages(data['posts'][0],9,22);pin=card(data['posts'][0],pp[0],0,len(pp),cache,22,True)
            im=composite(c,style,pin)
            if style!='grid':
                import cv2
                cap=cv2.VideoCapture(self.bg.get());cap.set(cv2.CAP_PROP_POS_MSEC,1500);ok,fr=cap.read();cap.release()
                if ok:
                    from PIL import ImageOps
                    bg=ImageOps.fit(Image.fromarray(cv2.cvtColor(fr,cv2.COLOR_BGR2RGB)),(720,1280));bg.paste(im,mask=im.getchannel('A'));im=bg
                else:
                    bg=Image.new('RGB',(720,1280),'#164e46');bg.paste(im,mask=im.getchannel('A'));im=bg
            self.preview_img=ctk.CTkImage(im,size=(int(self.preview_height*9/16),self.preview_height));self.preview_label.configure(image=self.preview_img,text='')
        except Exception as e:self.log('Xem trước: '+str(e))

    def export(self):
        if self.busy:return
        try:
            d=self.data();count=int(self.count.get());speed=int(self.speed.get())
            if not 1<=count<=200:raise ValueError('Số bài từ 1 đến 200.')
            if not 60<=speed<=400:raise ValueError('Tốc độ từ 60 đến 400 từ/phút.')
            args=dict(style=STYLES[self.style.get()],background=self.bg.get(),music=self.music.get(),voice=VOICES[self.voice.get()],speech=bool(self.speech.get()),speed=speed,max_posts=count,resolution=1080 if self.resolution.get().startswith('1080') else 720)
        except Exception as e:messagebox.showerror('Kiểm tra nội dung',str(e));return
        path=filedialog.asksaveasfilename(initialdir=str(ROOT/'outputs'),initialfile='threads_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.mp4',defaultextension='.mp4',filetypes=[('Video MP4','*.mp4')])
        if not path:return
        self.progress.set(0)
        def task():
            out=render(d,path,**args,log=self.log,progress=lambda p:self.events.put(('progress',p)),cancel=self.cancel)
            self.events.put(('output',out))
        self.start(task)

    def poll(self):
        while not self.events.empty():
            kind,value=self.events.get()
            if kind=='log':self.logbox.insert('end',value+'\n');self.logbox.see('end')
            elif kind=='data':self.set_data(value);self.preview_index=0;self.preview()
            elif kind=='progress':self.progress.set(value)
            elif kind=='error':self.logbox.insert('end',value+'\n');messagebox.showerror('Thông báo',value)
            elif kind=='done':self.busy=False;self.fetch_button.configure(state='normal');self.export_button.configure(state='normal')
            elif kind=='output':self.last_output=str(value);messagebox.showinfo('Xuất video thành công',str(value))
        self.after(150,self.poll)

    def open_output(self):
        if self.last_output:os.startfile(self.last_output)
        else:os.startfile(ROOT/'outputs')

    def close(self):
        if self.busy:
            self.cancel.set();self.log('Đang dừng tác vụ, hãy chờ trước khi đóng cửa sổ.');return
        self.destroy()


if __name__=='__main__':Studio().mainloop()
