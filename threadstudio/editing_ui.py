import hashlib
import json
import shutil
from pathlib import Path
from tkinter import filedialog,messagebox

import customtkinter as ctk

from .render import ROOT,probe
from .editing import media_info,preview_frame,normalize,scene_timeline


class EditingPanel:
    def __init__(self,app,tab):
        self.app=app;self.items=[];self.selected=None;self.source=None;self.preview_busy=False
        app.heading(tab,'Chèn meme, ảnh và video','Chọn video từ Thư viện để chỉnh bản có sẵn. Hoặc lưu bộ media và áp dụng khi tạo video hàng loạt. Thời gian tính bằng giây; vị trí dựa trên khung 720 × 1280, tự co giãn khi xuất 1080p.')
        body=ctk.CTkFrame(tab,fg_color='transparent');body.pack(fill='both',expand=True)
        form=ctk.CTkScrollableFrame(body);form.pack(side='left',fill='both',expand=True,padx=8,pady=6)
        right=ctk.CTkFrame(body,width=335);right.pack(side='right',fill='y',padx=8,pady=6);right.pack_propagate(False)
        self.selection=ctk.CTkOptionMenu(form,values=['Thêm media mới'],command=self.select);self.selection.pack(fill='x',padx=12,pady=6)
        row=ctk.CTkFrame(form,fg_color='transparent');row.pack(fill='x',padx=8)
        app.button(row,'Chọn meme / ảnh / clip',self.choose,width=200);app.button(row,'Xóa lớp chọn',self.remove,width=140)
        self.path=ctk.CTkEntry(form,placeholder_text='Tệp media');self.path.pack(fill='x',padx=12,pady=5)
        self.mode=ctk.CTkOptionMenu(form,values=['Phủ lên video','Chèn đoạn rồi tiếp tục']);self.mode.pack(fill='x',padx=12,pady=5)
        self.fields={}
        for key,label,value in [('scene','Cảnh (0 = toàn video)','0'),('start','Bắt đầu / điểm chèn (giây)','0'),('duration','Thời lượng (giây)','3'),('offset','Bắt đầu trong clip nguồn (giây)','0'),('x','X (px)','40'),('y','Y (px)','850'),('width','Chiều rộng (px)','280'),('opacity','Độ hiện (0–1)','1'),('volume','Âm lượng clip (0–2)','0.7')]:
            row=ctk.CTkFrame(form,fg_color='transparent');row.pack(fill='x',padx=12,pady=3);ctk.CTkLabel(row,text=label,width=270,anchor='w').pack(side='left');e=ctk.CTkEntry(row);e.pack(side='left',fill='x',expand=True);e.insert(0,value);self.fields[key]=e
        self.audio=ctk.CTkCheckBox(form,text='Dùng âm thanh từ clip (ảnh luôn không tiếng)');self.audio.pack(anchor='w',padx=12,pady=8)
        row=ctk.CTkFrame(form,fg_color='transparent');row.pack(fill='x',padx=8)
        app.button(row,'Lưu lớp media',self.apply,width=150);app.button(row,'Phủ toàn khung',self.full_frame,width=155)
        app.heading(form,'Bộ media của dự án','Lớp phủ phía sau nằm trên lớp phía trước. Chèn đoạn sẽ tạm dừng video gốc và giữ tiếng gốc khi tiếp tục. Với Cảnh = 0, thời điểm lớp phủ tính trên video sau khi chèn; điểm chèn đoạn tính trên video gốc.')
        row=ctk.CTkFrame(form,fg_color='transparent');row.pack(fill='x',padx=8)
        app.button(row,'Lưu bộ media',self.save_set,width=145);app.button(row,'Mở bộ media',self.load_set,width=145)
        self.use_batch=ctk.CTkCheckBox(form,text='Áp dụng bộ media này khi thêm lô video mới');self.use_batch.pack(anchor='w',padx=12,pady=8)
        self.summary=ctk.CTkLabel(form,text='Chưa có media',anchor='w',justify='left',wraplength=550);self.summary.pack(fill='x',padx=12,pady=8)
        ctk.CTkButton(right,text='Dùng video chọn trong Thư viện',command=self.use_selected).pack(fill='x',padx=10,pady=10)
        self.source_label=ctk.CTkLabel(right,text='Chưa chọn video nguồn',wraplength=300);self.source_label.pack(fill='x',padx=10)
        self.preview_height=max(140,min(280,app.winfo_screenheight()-620))
        self.preview=ctk.CTkLabel(right,text='Xem trước ở thời điểm bên dưới',height=self.preview_height);self.preview.pack(fill='x',padx=10,pady=8)
        self.seek=ctk.CTkEntry(right,placeholder_text='Thời điểm xem trước');self.seek.insert(0,'0');self.seek.pack(fill='x',padx=10,pady=4)
        ctk.CTkButton(right,text='Cập nhật xem trước',command=self.show_preview).pack(fill='x',padx=10,pady=4)
        ctk.CTkButton(right,text='XUẤT BẢN CHỈNH SỬA',command=self.export).pack(fill='x',padx=10,pady=8)

    def choices(self):return ['Thêm media mới']+[f'{i+1}. {Path(e["path"]).name} · {e["start"]}s' for i,e in enumerate(self.items)]
    def refresh(self):
        self.selection.configure(values=self.choices());self.summary.configure(text='\n'.join(f'{i+1}. {"Phủ" if e["mode"]=="overlay" else "Chèn"} · {Path(e["path"]).name} · {e["duration"]}s · cảnh {e.get("scene",0)}' for i,e in enumerate(self.items)) or 'Chưa có media')
        if self.selected is not None and self.selected<len(self.items):self.selection.set(self.choices()[self.selected+1])

    def choose(self):
        path=filedialog.askopenfilename(filetypes=[('Ảnh, meme và video','*.png *.jpg *.jpeg *.webp *.bmp *.gif *.mp4 *.mov *.mkv *.webm')])
        if not path:return
        try:
            media_info(path);self.path.delete(0,'end');self.path.insert(0,path);self.selected=None;self.selection.set('Thêm media mới')
        except Exception as e:messagebox.showerror('Media không hợp lệ',str(e))

    def select(self,label):
        if label=='Thêm media mới':self.selected=None;return
        i=int(label.split('.')[0])-1;self.selected=i;e=self.items[i]
        self.path.delete(0,'end');self.path.insert(0,e['path']);self.mode.set('Phủ lên video' if e['mode']=='overlay' else 'Chèn đoạn rồi tiếp tục')
        for key,entry in self.fields.items():entry.delete(0,'end');entry.insert(0,str(e.get(key,0)))
        self.audio.select() if e.get('audio') else self.audio.deselect()

    def apply(self):
        try:
            source=Path(self.path.get());media_info(source)
            item={k:float(e.get()) for k,e in self.fields.items()};item['scene']=int(item['scene']);item.update(path=str(source.resolve()),mode='overlay' if self.mode.get()=='Phủ lên video' else 'insert',audio=bool(self.audio.get()))
            # Check file and numeric ranges now; real scene and duration validation happens against each video.
            normalize([dict(item,scene=0,start=0)],max(1,item['duration']))
            folder=ROOT/'data'/'media_assets';folder.mkdir(exist_ok=True)
            with source.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()[:20]
            target=folder/(digest+source.suffix.lower())
            if not target.exists():shutil.copy2(source,target)
            item['path']=str(target)
            if self.selected is None:self.items.append(item);self.selected=len(self.items)-1
            else:self.items[self.selected]=item
            self.refresh();self.app.notify('Đã lưu lớp media. Có thể xem trước hoặc xuất bản mới.')
        except Exception as e:messagebox.showerror('Kiểm tra media',str(e),parent=self.app)

    def remove(self):
        if self.selected is not None:self.items.pop(self.selected);self.selected=None;self.selection.set('Thêm media mới');self.refresh()

    def full_frame(self):
        for key,value in [('x','0'),('y','0'),('width','720')]:self.fields[key].delete(0,'end');self.fields[key].insert(0,value)
        self.app.notify('Đã đặt rộng 720 px, giữ tỷ lệ ảnh/clip. Bấm Lưu lớp media để áp dụng.')

    def save_set(self):
        p=filedialog.asksaveasfilename(defaultextension='.json',filetypes=[('Bộ media','*.json')])
        if p:Path(p).write_text(json.dumps({'edits':self.items},ensure_ascii=False,indent=2),encoding='utf8')
    def load_set(self):
        p=filedialog.askopenfilename(filetypes=[('Bộ media','*.json')])
        if not p:return
        try:
            items=json.loads(Path(p).read_text(encoding='utf8'))['edits']
            for item in items:media_info(item['path'])
            self.items=items;self.selected=None;self.selection.set('Thêm media mới');self.refresh()
        except Exception as e:messagebox.showerror('Không mở được bộ media',str(e))

    def use_selected(self):
        records=self.app.selected_records()
        if len(records)!=1:messagebox.showinfo('Chọn video','Chọn đúng một video ở Thư viện rồi quay lại đây.');return
        self.source=records[0];info=probe(self.source['path']);self.source_label.configure(text=self.source['title']+'\n'+f"{float(info['format']['duration']):.1f}s · {len(scene_timeline(self.source['path']))} cảnh")
        self.show_preview()

    def show_preview(self):
        if self.preview_busy:return
        if not self.source:messagebox.showinfo('Chọn nguồn','Dùng video chọn trong Thư viện trước.');return
        try:t=float(self.seek.get());items=json.loads(json.dumps(self.items));path=self.source['path']
        except Exception as e:messagebox.showerror('Thời điểm',str(e));return
        self.preview_busy=True
        def task():
            try:
                im,total=preview_frame(path,items,t);im.thumbnail((240,self.preview_height));self.app.events.put(('media_preview',(im,total)))
            finally:self.preview_busy=False
        self.app.background(task)

    def export(self):
        if not self.source or not self.items:messagebox.showinfo('Chọn nguồn và media','Chọn video nguồn và lưu ít nhất một lớp media trước.');return
        try:
            normalize(self.items,float(probe(self.source['path'])['format']['duration']),scene_timeline(self.source['path']))
            options={'operation':'edit','edits':json.loads(json.dumps(self.items)),'caption':self.source['caption']}
            self.app.store.add_job(self.source['title']+'_edit',self.source['path'],options,output_dir=self.app.output_dir.get());self.app.tabs.set('Hàng đợi');self.app.refresh();self.app.notify('Đã thêm bản chỉnh sửa vào hàng đợi. Bấm Bắt đầu chạy; video gốc được giữ nguyên.')
        except Exception as e:messagebox.showerror('Không xuất được bản chỉnh',str(e))
