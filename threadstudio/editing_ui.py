import hashlib
import json
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import ImageDraw

from .render import ROOT, probe
from .editing import media_info, preview_frame, normalize, scene_timeline, keyframe_state

MEDIA_TYPES = [('Ảnh, meme, video và âm thanh', '*.png *.jpg *.jpeg *.webp *.bmp *.gif *.mp4 *.mov *.mkv *.webm *.mp3 *.wav *.m4a *.aac *.ogg *.flac')]


class EditingPanel:
    def __init__(self, app, tab):
        self.app = app; self.items = []; self.selected = None; self.source = None; self.preview_busy = False
        self.playhead = 0.0; self._playing = False; self._drag = None; self._pv_size = (240, 280)
        app.heading(tab, 'Chèn meme, ảnh, video và âm thanh',
                    'Timeline bên dưới: bấm để tua, kéo khối để đổi thời điểm, bấm khối để chọn lớp. Trên khung xem trước: kéo để di chuyển lớp, lăn chuột để đổi kích thước. Thời gian tính bằng giây; vị trí dựa trên khung 720 × 1280.')
        bottom = ctk.CTkFrame(tab); bottom.pack(side='bottom', fill='x', padx=8, pady=6)
        transport = ctk.CTkFrame(bottom, fg_color='transparent'); transport.pack(fill='x')
        app.button(transport, '▶ Phát / ⏸ Dừng', self.toggle_play, width=130)
        app.button(transport, '◆ Ghi keyframe tại playhead', self.record_keyframe, width=210)
        app.button(transport, 'Xoá keyframe tại playhead', self.delete_keyframe, width=190)
        self.time_label = ctk.CTkLabel(transport, text='Playhead: 0.00s'); self.time_label.pack(side='left', padx=10)
        self.timeline = tk.Canvas(bottom, height=104, bg='#242424', highlightthickness=0)
        self.timeline.pack(fill='x', pady=(4, 2))
        self.timeline.bind('<Button-1>', self.tl_click); self.timeline.bind('<B1-Motion>', self.tl_drag)
        self.timeline.bind('<ButtonRelease-1>', self.tl_release); self.timeline.bind('<Configure>', lambda e: self.draw_timeline())
        body = ctk.CTkFrame(tab, fg_color='transparent'); body.pack(fill='both', expand=True)
        form = ctk.CTkScrollableFrame(body); form.pack(side='left', fill='both', expand=True, padx=8, pady=6)
        right = ctk.CTkFrame(body, width=335); right.pack(side='right', fill='y', padx=8, pady=6); right.pack_propagate(False)
        self.selection = ctk.CTkOptionMenu(form, values=['Thêm media mới'], command=self.select); self.selection.pack(fill='x', padx=12, pady=6)
        row = ctk.CTkFrame(form, fg_color='transparent'); row.pack(fill='x', padx=8)
        app.button(row, 'Chọn meme / ảnh / clip / nhạc', self.choose, width=215); app.button(row, 'Xóa lớp chọn', self.remove, width=120)
        row = ctk.CTkFrame(form, fg_color='transparent'); row.pack(fill='x', padx=8)
        app.button(row, 'Lớp lên trên', lambda: self.move_layer(1), width=120); app.button(row, 'Lớp xuống dưới', lambda: self.move_layer(-1), width=130)
        self.path = ctk.CTkEntry(form, placeholder_text='Tệp media'); self.path.pack(fill='x', padx=12, pady=5)
        self.mode = ctk.CTkOptionMenu(form, values=['Phủ lên video', 'Chèn đoạn rồi tiếp tục']); self.mode.pack(fill='x', padx=12, pady=5)
        self.fields = {}
        for key, label, value in [('scene', 'Cảnh (0 = toàn video)', '0'), ('start', 'Bắt đầu / điểm chèn (giây)', '0'),
                                  ('duration', 'Thời lượng (giây)', '3'), ('offset', 'Bắt đầu trong nguồn (giây)', '0'),
                                  ('x', 'X (px)', '40'), ('y', 'Y (px)', '850'), ('width', 'Chiều rộng (px)', '280'),
                                  ('opacity', 'Độ hiện (0–1)', '1'), ('volume', 'Âm lượng (0–2)', '0.7'),
                                  ('rotation', 'Xoay (độ, -360–360)', '0'), ('fade_in', 'Fade in (giây)', '0'), ('fade_out', 'Fade out (giây)', '0')]:
            row = ctk.CTkFrame(form, fg_color='transparent'); row.pack(fill='x', padx=12, pady=3)
            ctk.CTkLabel(row, text=label, width=270, anchor='w').pack(side='left')
            e = ctk.CTkEntry(row); e.pack(side='left', fill='x', expand=True); e.insert(0, value); self.fields[key] = e
        srow = ctk.CTkFrame(form, fg_color='transparent'); srow.pack(fill='x', padx=12, pady=3)
        ctk.CTkLabel(srow, text='Thanh trượt: Độ hiện / Âm lượng', width=270, anchor='w').pack(side='left')
        self.opacity_slider = ctk.CTkSlider(srow, from_=0, to=1, number_of_steps=100, width=110,
                                            command=lambda v: self._set_field('opacity', round(float(v), 2)))
        self.opacity_slider.pack(side='left', padx=2); self.opacity_slider.set(1)
        self.volume_slider = ctk.CTkSlider(srow, from_=0, to=2, number_of_steps=100, width=110,
                                           command=lambda v: self._set_field('volume', round(float(v), 2)))
        self.volume_slider.pack(side='left', padx=2); self.volume_slider.set(0.7)
        self.audio = ctk.CTkCheckBox(form, text='Dùng âm thanh từ clip (ảnh luôn không tiếng)'); self.audio.pack(anchor='w', padx=12, pady=6)
        crow = ctk.CTkFrame(form, fg_color='transparent'); crow.pack(fill='x', padx=12, pady=3)
        self.chroma_on = ctk.CTkCheckBox(crow, text='Tách nền (chroma key)'); self.chroma_on.pack(side='left')
        self.chroma_color = ctk.CTkEntry(crow, width=90); self.chroma_color.insert(0, '#00ff00'); self.chroma_color.pack(side='left', padx=6)
        ctk.CTkLabel(crow, text='Độ nhạy').pack(side='left')
        self.chroma_sim = ctk.CTkSlider(crow, from_=0, to=0.8, number_of_steps=80, width=110); self.chroma_sim.set(0.35); self.chroma_sim.pack(side='left', padx=4)
        prow = ctk.CTkFrame(form, fg_color='transparent'); prow.pack(fill='x', padx=8)
        app.button(prow, 'Preset: Fade', lambda: self.preset('fade'), width=105)
        app.button(prow, 'Trượt từ dưới', lambda: self.preset('slide'), width=115)
        app.button(prow, 'Zoom in', lambda: self.preset('zoom'), width=90)
        app.button(prow, 'Pop meme', lambda: self.preset('pop'), width=100)
        self.kf_label = ctk.CTkLabel(form, text='Keyframe: chưa có', anchor='w', justify='left', wraplength=550)
        self.kf_label.pack(fill='x', padx=12, pady=4)
        row = ctk.CTkFrame(form, fg_color='transparent'); row.pack(fill='x', padx=8)
        app.button(row, 'Lưu lớp media', self.apply, width=150); app.button(row, 'Phủ toàn khung', self.full_frame, width=155)
        app.heading(form, 'Bộ media của dự án', 'Lớp phủ phía sau nằm trên lớp phía trước. Chèn đoạn sẽ tạm dừng video gốc và giữ tiếng gốc khi tiếp tục. Lớp có keyframe/chroma/fade/xoay được dựng từng khung hình nên chậm hơn lớp tĩnh một chút.')
        row = ctk.CTkFrame(form, fg_color='transparent'); row.pack(fill='x', padx=8)
        app.button(row, 'Lưu bộ media', self.save_set, width=145); app.button(row, 'Mở bộ media', self.load_set, width=145)
        self.use_batch = ctk.CTkCheckBox(form, text='Áp dụng bộ media này khi thêm lô video mới'); self.use_batch.pack(anchor='w', padx=12, pady=8)
        self.summary = ctk.CTkLabel(form, text='Chưa có media', anchor='w', justify='left', wraplength=550); self.summary.pack(fill='x', padx=12, pady=8)
        ctk.CTkButton(right, text='Dùng video chọn trong Thư viện', command=self.use_selected).pack(fill='x', padx=10, pady=10)
        self.source_label = ctk.CTkLabel(right, text='Chưa chọn video nguồn', wraplength=300); self.source_label.pack(fill='x', padx=10)
        self.preview_height = max(140, min(280, app.winfo_screenheight() - 620))
        self.preview = ctk.CTkLabel(right, text='Xem trước ở thời điểm bên dưới', height=self.preview_height); self.preview.pack(fill='x', padx=10, pady=8)
        self.preview.bind('<Button-1>', self.pv_down); self.preview.bind('<B1-Motion>', self.pv_move)
        self.preview.bind('<ButtonRelease-1>', lambda e: self.show_preview()); self.preview.bind('<MouseWheel>', self.pv_wheel)
        self.seek = ctk.CTkEntry(right, placeholder_text='Thời điểm xem trước'); self.seek.insert(0, '0'); self.seek.pack(fill='x', padx=10, pady=4)
        ctk.CTkButton(right, text='Cập nhật xem trước', command=self.show_preview).pack(fill='x', padx=10, pady=4)
        ctk.CTkButton(right, text='XUẤT BẢN CHỈNH SỬA', command=self.export).pack(fill='x', padx=10, pady=8)

    # ---------- helpers ----------
    def _set_field(self, key, value):
        e = self.fields[key]; e.delete(0, 'end'); e.insert(0, str(value))

    def _total(self):
        if self.source:
            try:
                dur = float(probe(self.source['path'])['format']['duration'])
                try:
                    _, total = normalize(json.loads(json.dumps(self.items)), dur, scene_timeline(self.source['path']))
                    return total
                except Exception:
                    return dur
            except Exception:
                pass
        ends = [float(i.get('start', 0)) + float(i.get('duration', 0)) for i in self.items]
        return max(ends) if ends else 30.0

    def _selected_item(self):
        return self.items[self.selected] if self.selected is not None and self.selected < len(self.items) else None

    def choices(self):
        return ['Thêm media mới'] + [f'{i + 1}. {Path(e["path"]).name} · {e["start"]}s' for i, e in enumerate(self.items)]

    def refresh(self):
        self.selection.configure(values=self.choices())
        label = {'overlay': 'Phủ', 'insert': 'Chèn', 'audio': 'Nhạc'}
        self.summary.configure(text='\n'.join(
            f'{i + 1}. {label.get(e.get("mode", "overlay"), "Phủ")} · {Path(e["path"]).name} · {e["duration"]}s · cảnh {e.get("scene", 0)}'
            f'{" · ◆" + str(len(e["keyframes"])) if e.get("keyframes") else ""}{" · tách nền" if e.get("chroma") else ""}'
            for i, e in enumerate(self.items)) or 'Chưa có media')
        if self.selected is not None and self.selected < len(self.items):
            self.selection.set(self.choices()[self.selected + 1]); self._show_keyframes(self.items[self.selected])
        self.draw_timeline()

    def _show_keyframes(self, item):
        kfs = item.get('keyframes') or []
        self.kf_label.configure(text='Keyframe: ' + (', '.join(f'{k["t"]:.2f}s' for k in kfs) if kfs else 'chưa có'))

    # ---------- timeline ----------
    def _tl_map(self):
        w = max(80, self.timeline.winfo_width() - 16); total = self._total()
        return (lambda t: 8 + w * t / total if total > 0 else 8), total

    def draw_timeline(self):
        try:
            c = self.timeline; c.delete('all'); x_of, total = self._tl_map()
        except Exception:
            return
        for s in range(0, int(total) + 1, max(1, int(total // 8) or 1)):
            x = x_of(s); c.create_line(x, 4, x, 20, fill='#666'); c.create_text(x + 2, 6, text=f'{s}s', anchor='nw', fill='#999', font=('TkDefaultFont', 7))
        if self.source:
            try:
                for i, sc in enumerate(scene_timeline(self.source['path'])):
                    c.create_rectangle(x_of(sc['start']), 22, x_of(sc['start'] + sc['duration']), 38,
                                       fill='#333' if i % 2 == 0 else '#3d3d3d', outline='#555')
                    c.create_text(x_of(sc['start']) + 3, 25, text=f'Cảnh {i + 1}', anchor='nw', fill='#bbb', font=('TkDefaultFont', 7))
            except Exception:
                pass
        for i, e in enumerate(self.items):
            mode = e.get('mode', 'overlay'); y0, y1 = (66, 84) if mode == 'audio' else (40, 64)
            if mode == 'insert':
                x = x_of(float(e['start'])); c.create_polygon(x - 5, 4, x + 5, 4, x, 14, fill='#ffb74d', outline='')
                continue
            fill = '#3f9e4d' if mode == 'audio' else '#3a7ca5'
            c.create_rectangle(x_of(float(e['start'])), y0, x_of(float(e['start']) + float(e['duration'])), y1,
                               fill=fill, outline='#ffd166' if i == self.selected else '#222', width=2 if i == self.selected else 1)
            c.create_text(x_of(float(e['start'])) + 3, y0 + 2, text=Path(e['path']).name[:22], anchor='nw', fill='white', font=('TkDefaultFont', 7))
            for k in e.get('keyframes') or []:
                kx = x_of(float(e['start']) + float(k['t'])); cy = (y0 + y1) / 2
                c.create_polygon(kx, cy - 5, kx + 5, cy, kx, cy + 5, kx - 5, cy, fill='#ffd166', outline='')
        px = x_of(self.playhead); c.create_line(px, 2, px, 100, fill='#ff5252', width=2)

    def _tl_time(self, event):
        x_of, total = self._tl_map(); w = max(80, self.timeline.winfo_width() - 16)
        return min(max(0.0, (event.x - 8) / w * total), total)

    def tl_click(self, event):
        t = self._tl_time(event); self._drag = None
        for i, e in enumerate(self.items):
            if e.get('mode') == 'insert':
                continue
            y0, y1 = (66, 84) if e.get('mode') == 'audio' else (40, 64)
            if y0 <= event.y <= y1 and float(e['start']) <= t <= float(e['start']) + float(e['duration']):
                self.select(self.choices()[i + 1]); self._drag = ('block', i, t - float(e['start'])); break
        self._set_playhead(t)

    def tl_drag(self, event):
        t = self._tl_time(event)
        if self._drag and self._drag[0] == 'block':
            _, i, grab = self._drag; item = self.items[i]
            item['start'] = round(max(0.0, t - grab), 2); self._set_field('start', item['start']); self.draw_timeline()
        else:
            self._set_playhead(t, preview=False)

    def tl_release(self, event):
        self._drag = None; self.refresh(); self.show_preview()

    def _set_playhead(self, t, preview=True):
        self.playhead = round(float(t), 2); self.seek.delete(0, 'end'); self.seek.insert(0, str(self.playhead))
        self.time_label.configure(text=f'Playhead: {self.playhead:.2f}s / {self._total():.1f}s'); self.draw_timeline()
        if preview:
            self.show_preview()

    def toggle_play(self):
        self._playing = not self._playing
        if self._playing:
            self._tick()

    def _tick(self):
        if not self._playing:
            return
        t = self.playhead + 0.12
        if t >= self._total():
            self._playing = False; return
        self._set_playhead(t)
        self.timeline.after(150, self._tick)

    # ---------- preview drag / resize ----------
    def _pv_to_video(self, event):
        w, h = self.preview.winfo_width(), self.preview.winfo_height(); pw, ph = self._pv_size
        return (event.x - (w - pw) / 2) / pw * 720, (event.y - (h - ph) / 2) / ph * 1280

    def _state_now(self, item):
        return keyframe_state(item, min(max(0.0, self.playhead - float(item['start'])), float(item['duration'])))

    def pv_down(self, event):
        item = self._selected_item()
        if not item or item.get('mode') != 'overlay':
            return
        gx, gy = self._pv_to_video(event); st = self._state_now(item)
        try:
            info = media_info(item['path']); aspect = info['height'] / info['width'] if info['width'] else 1
        except Exception:
            aspect = 1
        if st['x'] <= gx <= st['x'] + st['width'] and st['y'] <= gy <= st['y'] + st['width'] * aspect:
            self._drag = ('pv', gx - st['x'], gy - st['y'])

    def pv_move(self, event):
        if not self._drag or self._drag[0] != 'pv':
            return
        item = self._selected_item()
        if not item:
            return
        gx, gy = self._pv_to_video(event)
        self._apply_xy(item, round(gx - self._drag[1]), round(gy - self._drag[2]))

    def pv_wheel(self, event):
        item = self._selected_item()
        if not item or item.get('mode') != 'overlay':
            return
        step = 10 if event.delta > 0 else -10; st = self._state_now(item)
        self._apply_xy(item, None, None, width=min(1440, max(16, st['width'] + step)))

    def _apply_xy(self, item, x, y, width=None):
        tl = self.playhead - float(item['start'])
        if item.get('keyframes') and 0 <= tl <= float(item['duration']):
            st = self._state_now(item); new = {'t': round(tl, 2)}
            for k in ('x', 'y', 'width', 'opacity', 'rotation'):
                new[k] = st[k]
            if x is not None: new['x'] = float(x)
            if y is not None: new['y'] = float(y)
            if width is not None: new['width'] = float(width)
            kfs = [k for k in item['keyframes'] if abs(k['t'] - new['t']) > 0.05] + [new]
            item['keyframes'] = sorted(kfs, key=lambda k: k['t']); self._show_keyframes(item)
        else:
            if x is not None: item['x'] = float(x); self._set_field('x', int(x))
            if y is not None: item['y'] = float(y); self._set_field('y', int(y))
            if width is not None: item['width'] = float(width); self._set_field('width', int(width))
        self.draw_timeline()

    # ---------- keyframes & presets ----------
    def record_keyframe(self):
        item = self._selected_item()
        if not item or item.get('mode') != 'overlay':
            self.app.notify('Chọn một lớp phủ (ảnh/video) trước khi ghi keyframe.'); return
        tl = self.playhead - float(item['start'])
        if not 0 <= tl <= float(item['duration']):
            self.app.notify('Playhead phải nằm trong khoảng thời gian của lớp đã chọn.'); return
        try:
            st = {k: float(self.fields[k].get()) for k in ('x', 'y', 'width', 'opacity', 'rotation')}
        except Exception:
            self.app.notify('Thông số X/Y/rộng/độ hiện/xoay chưa hợp lệ.'); return
        new = {'t': round(tl, 2), **st}
        item['keyframes'] = sorted([k for k in item.get('keyframes', []) if abs(k['t'] - new['t']) > 0.05] + [new], key=lambda k: k['t'])
        self._show_keyframes(item); self.draw_timeline(); self.app.notify(f'Đã ghi keyframe tại {tl:.2f}s của lớp.')

    def delete_keyframe(self):
        item = self._selected_item()
        if not item:
            return
        tl = self.playhead - float(item['start'])
        item['keyframes'] = [k for k in item.get('keyframes', []) if abs(k['t'] - tl) > 0.05]
        self._show_keyframes(item); self.draw_timeline()

    def preset(self, kind):
        item = self._selected_item()
        if not item:
            self.app.notify('Chọn một lớp media trước khi dùng preset.'); return
        if kind == 'fade':
            item['fade_in'] = 0.5; item['fade_out'] = 0.5
            self._set_field('fade_in', 0.5); self._set_field('fade_out', 0.5)
        elif item.get('mode') == 'overlay':
            st = self._state_now(item); dur = float(item['duration'])
            keep = [k for k in item.get('keyframes', []) if k['t'] > 0.65]
            if kind == 'slide':
                item['keyframes'] = [{'t': 0, 'x': st['x'], 'y': st['y'] + 320, 'width': st['width'], 'opacity': 0, 'rotation': st['rotation']},
                                     {'t': 0.6, 'x': st['x'], 'y': st['y'], 'width': st['width'], 'opacity': st['opacity'], 'rotation': st['rotation']}] + keep
            elif kind == 'zoom':
                item['keyframes'] = [{'t': 0, 'x': st['x'], 'y': st['y'], 'width': st['width'] * 0.6, 'opacity': st['opacity'], 'rotation': st['rotation']},
                                     {'t': dur, 'x': st['x'], 'y': st['y'], 'width': st['width'], 'opacity': st['opacity'], 'rotation': st['rotation']}]
            elif kind == 'pop':
                cx, cy = st['x'] + st['width'] / 2, st['y'] + st['width'] / 2
                def at(w):
                    return {'x': cx - w / 2, 'y': cy - w / 2, 'width': w, 'opacity': st['opacity'], 'rotation': st['rotation']}
                item['keyframes'] = [{'t': 0, **at(st['width'] * 0.5)}, {'t': 0.18, **at(st['width'] * 1.08)}, {'t': 0.3, **at(st['width'])}] + keep
            self._show_keyframes(item)
        self.refresh(); self.show_preview()

    # ---------- layer CRUD ----------
    def choose(self):
        path = filedialog.askopenfilename(filetypes=MEDIA_TYPES)
        if not path:
            return
        try:
            media_info(path); self.path.delete(0, 'end'); self.path.insert(0, path)
            self.selected = None; self.selection.set('Thêm media mới')
        except Exception as e:
            messagebox.showerror('Media không hợp lệ', str(e))

    def select(self, label):
        if label == 'Thêm media mới':
            self.selected = None; return
        i = int(label.split('.')[0]) - 1; self.selected = i; e = self.items[i]
        self.path.delete(0, 'end'); self.path.insert(0, e['path'])
        self.mode.set('Chèn đoạn rồi tiếp tục' if e.get('mode') == 'insert' else 'Phủ lên video')
        for key, entry in self.fields.items():
            entry.delete(0, 'end'); entry.insert(0, str(e.get(key, 0)))
        self.opacity_slider.set(float(e.get('opacity', 1))); self.volume_slider.set(float(e.get('volume', 0.7)))
        self.audio.select() if e.get('audio') else self.audio.deselect()
        ch = e.get('chroma')
        if ch:
            self.chroma_on.select(); self.chroma_color.delete(0, 'end'); self.chroma_color.insert(0, ch.get('color', '#00ff00'))
            self.chroma_sim.set(float(ch.get('similarity', 0.35)))
        else:
            self.chroma_on.deselect()
        self._show_keyframes(e); self.draw_timeline()

    def apply(self):
        try:
            source = Path(self.path.get()); info = media_info(source)
            item = {k: float(e.get()) for k, e in self.fields.items()}; item['scene'] = int(item['scene'])
            mode = 'audio' if info.get('audio_only') else ('insert' if self.mode.get() == 'Chèn đoạn rồi tiếp tục' else 'overlay')
            item.update(path=str(source.resolve()), mode=mode, audio=bool(self.audio.get()))
            if self.chroma_on.get() and mode == 'overlay':
                item['chroma'] = {'color': self.chroma_color.get().strip() or '#00ff00',
                                  'similarity': float(self.chroma_sim.get()), 'blend': 0.15}
            old = self._selected_item()
            if old is not None and old.get('keyframes'):
                item['keyframes'] = old['keyframes']  # keyframes are edited via timeline buttons, not this form
            normalize([dict(item, scene=0, start=0)], max(1, item['duration']))
            folder = ROOT / 'data' / 'media_assets'; folder.mkdir(exist_ok=True)
            with source.open('rb') as f:
                digest = hashlib.file_digest(f, 'sha256').hexdigest()[:20]
            target = folder / (digest + source.suffix.lower())
            if not target.exists():
                shutil.copy2(source, target)
            item['path'] = str(target)
            if self.selected is None:
                self.items.append(item); self.selected = len(self.items) - 1
            else:
                self.items[self.selected] = item
            self.refresh(); self.app.notify('Đã lưu lớp media. Có thể xem trước hoặc xuất bản mới.')
        except Exception as e:
            messagebox.showerror('Kiểm tra media', str(e), parent=self.app)

    def remove(self):
        if self.selected is not None:
            self.items.pop(self.selected); self.selected = None; self.selection.set('Thêm media mới'); self.refresh()

    def move_layer(self, delta):
        if self.selected is None:
            return
        j = self.selected + delta
        if 0 <= j < len(self.items):
            self.items[self.selected], self.items[j] = self.items[j], self.items[self.selected]
            self.selected = j; self.refresh()

    def full_frame(self):
        for key, value in [('x', '0'), ('y', '0'), ('width', '720')]:
            self._set_field(key, value)
        self.app.notify('Đã đặt rộng 720 px, giữ tỷ lệ ảnh/clip. Bấm Lưu lớp media để áp dụng.')

    def save_set(self):
        p = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('Bộ media', '*.json')])
        if p:
            Path(p).write_text(json.dumps({'edits': self.items}, ensure_ascii=False, indent=2), encoding='utf8')

    def load_set(self):
        p = filedialog.askopenfilename(filetypes=[('Bộ media', '*.json')])
        if not p:
            return
        try:
            items = json.loads(Path(p).read_text(encoding='utf8'))['edits']
            for item in items:
                media_info(item['path'])
            self.items = items; self.selected = None; self.selection.set('Thêm media mới'); self.refresh()
        except Exception as e:
            messagebox.showerror('Không mở được bộ media', str(e))

    # ---------- source, preview, export ----------
    def use_selected(self):
        records = self.app.selected_records()
        if len(records) != 1:
            messagebox.showinfo('Chọn video', 'Chọn đúng một video ở Thư viện rồi quay lại đây.'); return
        self.source = records[0]; info = probe(self.source['path'])
        self.source_label.configure(text=self.source['title'] + '\n' + f"{float(info['format']['duration']):.1f}s · {len(scene_timeline(self.source['path']))} cảnh")
        self._set_playhead(0)

    def show_preview(self):
        if self.preview_busy:
            return
        if not self.source:
            messagebox.showinfo('Chọn nguồn', 'Dùng video chọn trong Thư viện trước.'); return
        try:
            t = float(self.seek.get()); items = json.loads(json.dumps(self.items)); path = self.source['path']
        except Exception as e:
            messagebox.showerror('Thời điểm', str(e)); return
        self.playhead = t; self.preview_busy = True
        selected, sel_item = self.selected, self._selected_item()

        def task():
            try:
                im, total = preview_frame(path, items, t)
                if sel_item and sel_item.get('mode') == 'overlay' and float(sel_item['start']) <= t < float(sel_item['start']) + float(sel_item['duration']):
                    st = keyframe_state(json.loads(json.dumps(sel_item)), t - float(sel_item['start']))
                    try:
                        info = media_info(sel_item['path']); h = st['width'] * info['height'] / info['width'] if info['width'] else st['width']
                    except Exception:
                        h = st['width']
                    d = ImageDraw.Draw(im)
                    d.rectangle([st['x'], st['y'], st['x'] + st['width'], st['y'] + h], outline=(255, 209, 102), width=4)
                    d.rectangle([st['x'] + st['width'] - 14, st['y'] + h - 14, st['x'] + st['width'] + 2, st['y'] + h + 2], fill=(255, 209, 102))
                im.thumbnail((240, self.preview_height)); self._pv_size = im.size
                self.app.events.put(('media_preview', (im, total)))
            finally:
                self.preview_busy = False
        self.app.background(task)

    def export(self):
        if not self.source or not self.items:
            messagebox.showinfo('Chọn nguồn và media', 'Chọn video nguồn và lưu ít nhất một lớp media trước.'); return
        try:
            normalize(self.items, float(probe(self.source['path'])['format']['duration']), scene_timeline(self.source['path']))
            options = {'operation': 'edit', 'edits': json.loads(json.dumps(self.items)), 'caption': self.source['caption']}
            self.app.store.add_job(self.source['title'] + '_edit', self.source['path'], options, output_dir=self.app.output_dir.get())
            self.app.tabs.set('Hàng đợi'); self.app.refresh(); self.app.notify('Đã thêm bản chỉnh sửa vào hàng đợi. Bấm Bắt đầu chạy; video gốc được giữ nguyên.')
        except Exception as e:
            messagebox.showerror('Không xuất được bản chỉnh', str(e))
