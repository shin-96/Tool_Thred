import asyncio
import io
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import uuid
import time
from pathlib import Path

import re
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent.parent
FONTS = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
W, H = 720, 1280
SPEECH_GATE=threading.Semaphore(1)
VOICE_COOLDOWN={}


class Cancelled(Exception):
    pass


def font(size, bold=False):
    return ImageFont.truetype(str(FONTS / ('arialbd.ttf' if bold else 'arial.ttf')), size)


def text_runs(text, size):
    import re
    # Segoe UI Emoji supplies glyphs that Arial lacks (including the sample's light bulb).
    for part in re.findall(r'[\U0001F000-\U0001FAFF\u2600-\u27ff\ufe0f\u200d]+|[^\U0001F000-\U0001FAFF\u2600-\u27ff\ufe0f\u200d]+',text):
        emoji=any(ord(c)>=0x1F000 or 0x2600<=ord(c)<=0x27ff for c in part)
        yield part,ImageFont.truetype(str(FONTS/'seguiemj.ttf'),size) if emoji else font(size)


def measure(d,text,size):
    return sum(d.textlength(s,font=f) for s,f in text_runs(text,size))


def draw_line(d,xy,text,size,fill):
    x,y=xy
    for part,f in text_runs(text,size):
        d.text((x,y),part,font=f,fill=fill,embedded_color=True)
        x+=d.textlength(part,font=f)


def run(cmd, cancel=None):
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with __import__('tempfile').TemporaryFile() as err:
        p = subprocess.Popen([str(x) for x in cmd], stdout=subprocess.DEVNULL, stderr=err, creationflags=flags)
        while p.poll() is None:
            if cancel and cancel.wait(.15):
                p.terminate(); p.wait(); raise Cancelled('Đã hủy xuất video.')
            if cancel is None:
                threading.Event().wait(.15)
        if p.returncode:
            err.seek(0)
            raise RuntimeError(err.read().decode('utf8', errors='replace')[-3500:])


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'quiet', '-show_format', '-show_streams', '-of', 'json', str(path)], creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))



def _google_tts(text, audio, cancel=None):
    """Independent fallback voice: Google Translate TTS (Vietnamese). The endpoint
    caps each request near 200 characters, so long text is read in chunks and the
    MP3 parts are joined; the render re-encodes the mix anyway."""
    import requests
    from urllib.parse import quote
    chunks, cur = [], ''
    for piece in re.split(r'(?<=[.!?…;])\s+', text.replace('\n', ' ')):
        for word in piece.split():
            while len(word) > 180:
                if cur: chunks.append(cur); cur = ''
                chunks.append(word[:180]); word = word[180:]
            if len(cur) + len(word) + 1 > 180:
                chunks.append(cur); cur = word
            else:
                cur = (cur + ' ' + word).strip()
    if cur: chunks.append(cur)
    chunks = [c for c in chunks if c.strip()]
    if not chunks: raise RuntimeError('Không có nội dung để đọc.')
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    parts = []
    for chunk in chunks:
        if cancel and cancel.is_set(): raise Cancelled('Đã hủy giọng đọc.')
        r = requests.get('https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=vi&q=' + quote(chunk), headers=headers, timeout=30)
        if r.status_code != 200 or len(r.content) < 400: raise RuntimeError(f'Giọng Google trả HTTP {r.status_code}.')
        parts.append(r.content)
    Path(audio).write_bytes(b''.join(parts))

def synthesize(text,voice,audio,log,cancel=None,fallback=True):
    import edge_tts
    candidates=[voice]
    if fallback and voice.startswith('vi-VN-'):candidates.append('en-US-EmmaMultilingualNeural')
    cache=ROOT/'assets'/'speech_cache';cache.mkdir(exist_ok=True)
    with SPEECH_GATE:
        last=None
        for candidate in candidates:
            cached=cache/(hashlib.sha256((candidate+text).encode()).hexdigest()+'.mp3')
            if cached.exists():
                try:probe(cached);shutil.copy2(cached,audio);return candidate
                except Exception:pass
            if candidate!=candidates[-1] and VOICE_COOLDOWN.get(candidate,0)>time.monotonic():continue
            if candidate!=voice:log('Giọng Việt chưa phản hồi. Đang dùng Emma đa ngôn ngữ theo lựa chọn dự phòng.')
            for attempt in range(3):
                if cancel and cancel.is_set():raise Cancelled('Đã hủy giọng đọc.')
                try:
                    asyncio.run(edge_tts.Communicate(text,candidate).save(str(audio)))
                    probe(audio)
                    tmp=cached.with_suffix('.'+uuid.uuid4().hex+'.tmp');shutil.copy2(audio,tmp);tmp.replace(cached)
                    return candidate
                except Exception as e:
                    last=e
                    if attempt<2:
                        log(f'Giọng đọc chưa trả âm thanh; thử lại ({attempt+2}/3)…')
                        if cancel and cancel.wait(1+attempt):raise Cancelled('Đã hủy giọng đọc.')
                        if cancel is None:threading.Event().wait(1+attempt)
            VOICE_COOLDOWN[candidate]=time.monotonic()+120
        if fallback:
            try:
                log('Giọng Microsoft chưa phản hồi. Đang dùng giọng Google dự phòng.')
                cached_g=cache/(hashlib.sha256(('google-vi'+text).encode()).hexdigest()+'.mp3')
                if cached_g.exists():
                    try:probe(cached_g);shutil.copy2(cached_g,audio);return 'google-vi'
                    except Exception:pass
                _google_tts(text,audio,cancel)
                probe(audio)
                tmp=cached_g.with_suffix('.'+uuid.uuid4().hex+'.tmp');shutil.copy2(audio,tmp);tmp.replace(cached_g)
                return 'google-vi'
            except Exception as e:
                last=e
        raise RuntimeError('Dịch vụ giọng đọc chưa phản hồi sau các lần thử. Có thể đổi giọng hoặc tắt giọng trong Sửa tác vụ rồi Thử lại. '+str(last))


def wrap(text, width, size=25):
    d = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    lines = []
    for para in text.split('\n'):
        line = ''
        for word in para.split():
            # Split unusually long URLs/words so no text escapes the card.
            while measure(d,word,size) > width:
                n = 1
                while n < len(word) and measure(d,word[:n+1],size) <= width:
                    n += 1
                if line: lines.append(line); line = ''
                lines.append(word[:n]); word = word[n:]
            attempt = (line + ' ' + word).strip()
            if measure(d,attempt,size) > width and line:
                lines.append(line); line = word
            else: line = attempt
        lines.append(line)
    return lines


def pages(post, max_lines=18, size=25):
    lines = wrap(post['text'], 548, size)
    return [lines[i:i+max_lines] for i in range(0, len(lines), max_lines)] or [['']]


def avatar(post, cache):
    key = post['username']
    path = cache / (''.join(c for c in key if c.isalnum()) + '.png')
    if path.exists():
        return Image.open(path).convert('RGB')
    try:
        url = post.get('avatar', '')
        if not url.startswith('https://'): return None
        r = requests.get(url, timeout=8); r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert('RGB'); im.save(path); return im
    except Exception:
        return None


def card(post, lines, index, total, cache, size=25, square=False):
    height = 122 + len(lines) * (size + 10) + 48
    im = Image.new('RGBA', (616, height), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, 615, height-1), radius=0 if square else 24, fill='white')
    av = avatar(post, cache)
    if av:
        av = av.resize((48, 48)); mask=Image.new('L',(48,48)); ImageDraw.Draw(mask).ellipse((0,0,47,47),fill=255); im.paste(av,(26,24),mask)
    else:
        d.ellipse((26,24,74,72),fill='#dce9df'); d.text((40,31),post['username'][:1].upper(),font=font(24,True),fill='#285a45')
    name=post['username'][:29]
    d.text((88,23),name,font=font(23,True),fill='#111111')
    if post.get('verified'):
        x=88+d.textlength(name,font=font(23,True))+8; d.ellipse((x,28,x+14,42),fill='#28a9dc')
    d.text((88,54),post.get('date',''),font=font(17),fill='#888888')
    d.text((565,25),'···',font=font(25),fill='#777777')
    if total>1: d.text((26,86),f'Trang {index+1}/{total}',font=font(16),fill='#468474')
    y=114
    for line in lines:
        draw_line(d,(26,y),line,size,'#101114');y+=size+10
    y=height-36
    stats=post.get('stats',[])
    counts=[]
    for label in ['Like','Comment','Repost','Share']:
        value=next((s[len(label):].strip() for s in stats if s.startswith(label)), '')
        counts.append(value)
    for i, count in enumerate(counts):
        x=28+i*140
        if i==0:
            d.line([(x+12,y+18),(x,y+7),(x,y+2),(x+5,y-1),(x+12,y+4),(x+19,y-1),(x+24,y+2),(x+24,y+7),(x+12,y+18)],fill='#555b60',width=2)
        elif i==1:
            d.rounded_rectangle((x,y,x+23,y+18),radius=7,outline='#555b60',width=2);d.line((x+4,y+16,x+2,y+22,x+10,y+18),fill='#555b60',width=2)
        elif i==2:
            d.line((x,y+6,x+23,y+6,x+18,y+1),fill='#555b60',width=2);d.line((x+23,y+15,x,y+15,x+5,y+20),fill='#555b60',width=2)
        else: d.line([(x,y),(x+24,y+10),(x+8,y+21),(x+9,y+11),(x,y)],fill='#555b60',width=2)
        d.text((x+32,y-2),count,font=font(17),fill='#555b60')
    return im


def grid():
    im=Image.new('RGB',(W,H));p=im.load()
    for y in range(H):
        b=int(8+70*(y/H)**3)
        for x in range(W):p[x,y]=(3,5+int(7*y/H),b)
    d=ImageDraw.Draw(im)
    for x in range(0,W,64):d.line((x,0,x,H),fill='#53546a',width=1)
    for y in range(0,H,64):d.line((0,y,W,y),fill='#53546a',width=1)
    return im


def composite(c, style, pinned=None):
    im=Image.new('RGBA',(W,H))
    if style=='grid':
        im=grid().convert('RGBA')
        if pinned:
            im.alpha_composite(pinned,(52,140)); y=140+pinned.height+40
        else:y=180
    elif style=='top': y=210
    else:y=(H-c.height)//2
    if style!='grid':
        shadow=Image.new('RGBA',(W,H));shadow.paste((0,0,0,110),(50,y+7,670,y+c.height+12));shadow=shadow.filter(ImageFilter.GaussianBlur(13));im.alpha_composite(shadow)
    im.alpha_composite(c,(52,y))
    return im


def render(data, output, style='center', background='', music='', voice='ms-MY-YasminNeural', speech=True, speed=175, max_posts=12, resolution=720, log=print, progress=lambda x:None, cancel=None, speech_fallback=True,voice_api=None,edits=None,funny_only=False,music_volume=0.12,voice_volume=1.0):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise RuntimeError('Cần FFmpeg và ffprobe trong PATH. Chạy CAI_DAT.cmd.')
    if style not in {'center','top','grid'}:raise ValueError('Mẫu không hợp lệ.')
    if not 60 <= int(speed) <= 400: raise ValueError('Tốc độ đọc phải từ 60 đến 400 từ/phút.')
    try:
        from .source import attach_media
        attach_media(data,log)
    except Exception:pass  # media is optional; never block a render on it
    from .comment_filter import select_posts
    posts=select_posts(data.get('posts',[]),int(max_posts),funny_only,log=log)
    if not posts: raise ValueError('Dự án chưa có bài viết.')
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists(): raise ValueError('Tên video đã tồn tại. Hãy chọn tên mới.')
    work=output.parent/(output.stem+'_project');work.mkdir(exist_ok=True)
    cache=work/'avatars';cache.mkdir(exist_ok=True)
    (work/'source.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    if style!='grid':
        background=Path(background) if background else ROOT/'assets'/'gameplay.mp4'
        if not background.is_file(): raise ValueError('Chọn video nền MP4 trước khi xuất.')
    if music and not Path(music).is_file():raise ValueError('Không tìm thấy nhạc nền.')
    segments=[]; pinned=None
    if style=='grid':
        # Keep a readable page of the original above each reply; never shrink full posts to illegibility.
        pp=pages(posts[0],max_lines=9,size=22)
        pinned=card(posts[0],pp[0],0,len(pp),cache,size=22,square=True)
    for pi,post in enumerate(posts):
        chunks=pages(post,max_lines=9 if style=='grid' else 18,size=22 if style=='grid' else 25)
        for ci,lines in enumerate(chunks):
            if cancel and cancel.is_set():raise Cancelled('Đã hủy chuẩn bị video.')
            c=card(post,lines,ci,len(chunks),cache,size=22 if style=='grid' else 25,square=style in {'grid','top'})
            frame=composite(c,style,pinned if pi>0 else None)
            if style=='grid' and pi>0 and 140+pinned.height+40+c.height>H-70:
                raise ValueError('Thẻ quá dài. Hãy chia nội dung trong dự án thành đoạn ngắn hơn.')
            png=work/f'card_{len(segments):03}.png';frame.save(png)
            media=None; media_box=None
            if ci==0:
                m=post.get('media') or {}
                if m.get('path') and Path(m['path']).is_file():media=(m.get('type','image'),m['path'])
            if media and style=='center':
                # Attached media is its own block UNDER the card (like the original post),
                # not a background: card moves to the top, media plays in the box below it.
                top=90; box_y=top+c.height+30; box_h=H-box_y-60
                if box_h>=240:
                    frame=Image.new('RGBA',(W,H))
                    shadow=Image.new('RGBA',(W,H));shadow.paste((0,0,0,110),(50,top+7,670,top+c.height+12));shadow=shadow.filter(ImageFilter.GaussianBlur(13));frame.alpha_composite(shadow)
                    frame.alpha_composite(c,(52,top));frame.save(png)
                    media_box=(60,box_y,600,box_h)
            segments.append({'text':' '.join(lines),'png':png,'author':post['username'],'media':media,'media_box':media_box})
    log(f'Đang dựng {len(segments)} cảnh từ {len(posts)} bài/bình luận…')
    parts=[]; timeline=[]; elapsed=0
    for i,s in enumerate(segments):
        if cancel and cancel.is_set():raise Cancelled('Đã hủy xuất video.')
        log(f"Cảnh {i+1}/{len(segments)} · @{s['author']}")
        png=s['png']
        audio=work/f'voice_{i:03}.mp3'
        actual_voice=None
        from .speech_text import expand_speech
        spoken=expand_speech(s['text'])  # card keeps the original text; only the voice reads the expanded form
        if speech:
            if voice_api:
                from .voice_api import synthesize_api
                actual_voice=synthesize_api(spoken,voice_api,audio,log,cancel)
            else:actual_voice=synthesize(spoken,voice,audio,log,cancel,speech_fallback)
            dur=float(probe(audio)['format']['duration'])+.5
        else:dur=max(3.5,len(spoken.split())/int(speed)*60+1.0)
        if s.get('media') and s['media'][0]=='video':
            try:run(['ffmpeg','-v','error','-stream_loop','-1','-i',s['media'][1],'-t','0.5','-f','null','-'],cancel)
            except Exception:log(f'Cảnh {i+1}: file video đính kèm không đọc được, dùng nền thường.');s={**s,'media':None,'media_box':None}
        out=work/f'segment_{i:03}.mp4';cmd=['ffmpeg','-hide_banner','-loglevel','error','-y']
        if style=='grid':
            cmd+=['-loop','1','-framerate','30','-i',png]
            vf=f'[0:v]scale={resolution}:{int(resolution*16/9)//2*2},format=yuv420p[v]';aidx=1
        elif s.get('media_box'):
            bx,by,bw,bh=s['media_box']
            cmd+=['-stream_loop','-1','-ss',str(elapsed%float(probe(background)['format']['duration'])),'-i',background,'-loop','1','-framerate','30','-i',png]
            if s['media'][0]=='video':cmd+=['-stream_loop','-1','-i',s['media'][1]]
            else:cmd+=['-loop','1','-framerate','30','-i',s['media'][1]]
            vf=f'[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1[bg];[2:v]scale={bw}:{bh}:force_original_aspect_ratio=decrease,pad={bw}:{bh}:(ow-iw)/2:(oh-ih)/2:color=black@0,format=rgba[m];[bg][m]overlay={bx}:{by}:shortest=1[tmp];[tmp][1:v]overlay=0:0:shortest=1,scale={resolution}:{int(resolution*16/9)//2*2},format=yuv420p[v]';aidx=3
        elif s.get('media') and s['media'][0]=='video':
            cmd+=['-stream_loop','-1','-i',s['media'][1],'-loop','1','-framerate','30','-i',png]
            vf=f'[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1[bg];[bg][1:v]overlay=0:0:shortest=1,scale={resolution}:{int(resolution*16/9)//2*2},format=yuv420p[v]';aidx=2
        elif s.get('media'):
            cmd+=['-loop','1','-framerate','30','-i',s['media'][1],'-loop','1','-framerate','30','-i',png]
            vf=f'[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1[bg];[bg][1:v]overlay=0:0:shortest=1,scale={resolution}:{int(resolution*16/9)//2*2},format=yuv420p[v]';aidx=2
        else:
            cmd+=['-stream_loop','-1','-ss',str(elapsed%float(probe(background)['format']['duration'])),'-i',background,'-loop','1','-framerate','30','-i',png]
            vf=f'[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1[bg];[bg][1:v]overlay=0:0:shortest=1,scale={resolution}:{int(resolution*16/9)//2*2},format=yuv420p[v]';aidx=2
        if speech:cmd+=['-i',audio]
        else:cmd+=['-f','lavfi','-i','anullsrc=r=44100:cl=stereo']
        cmd+=['-filter_complex_threads','2','-filter_complex',vf+f';[{aidx}:a]apad,aresample=44100[a]','-map','[v]','-map','[a]','-t',f'{dur:.3f}','-r','30','-c:v','libx264','-threads','4','-preset','veryfast','-crf','20','-c:a','aac','-ar','44100','-ac','2','-movflags','+faststart',out]
        run(cmd,cancel);parts.append(out);timeline.append({'start':round(elapsed,3),'duration':round(dur,3),'author':s['author'],'text':s['text'],'spoken':spoken,'voice':actual_voice});elapsed+=dur;progress((i+1)/(len(segments)+1))
    concat=work/'concat.txt';concat.write_text('\n'.join("file '"+p.name+"'" for p in parts),encoding='utf8')
    joined=work/'joined.mp4'
    run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',concat,'-c','copy','-movflags','+faststart',joined],cancel)
    staging=work/'final.mp4'
    if music:
        run(['ffmpeg','-v','error','-y','-i',joined,'-stream_loop','-1','-i',music,'-filter_complex',f'[0:a]volume={float(voice_volume):.3f}[v0];[1:a]volume={float(music_volume):.3f}[m];[v0][m]amix=inputs=2:duration=first:normalize=0[a]','-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-t',str(elapsed),'-movflags','+faststart',staging],cancel)
    elif float(voice_volume)!=1.0:
        run(['ffmpeg','-v','error','-y','-i',joined,'-filter_complex',f'[0:a]volume={float(voice_volume):.3f}[a]','-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-movflags','+faststart',staging],cancel)
    else:shutil.copy2(joined,staging)
    if edits:
        from .editing import edit_video,normalize
        normalized,_=normalize(edits,float(probe(staging)['format']['duration']),timeline)
        edited=work/'with_media.mp4'
        if edited.exists():edited.unlink()
        edit_video(staging,edited,edits,log=log,cancel=cancel,timeline=timeline);staging=edited
        inserts=[e for e in normalized if e['mode']=='insert']
        for scene in timeline:
            start=scene['start'];end=start+scene['duration']
            scene['start']=round(start+sum(e['duration'] for e in inserts if e['start']<=start),3)
            scene['duration']=round(scene['duration']+sum(e['duration'] for e in inserts if start<e['start']<end),3)
    info=probe(staging)
    if not any(x['codec_type']=='video' for x in info['streams']) or float(info['format']['duration'])<elapsed-1:raise RuntimeError('Kiểm tra video xuất thất bại.')
    staging.replace(output)
    (work/'timeline.json').write_text(json.dumps(timeline,ensure_ascii=False,indent=2),encoding='utf8')
    progress(1);log(f'Hoàn thành: {output} ({float(info["format"]["duration"]):.1f} giây)')
    return output
