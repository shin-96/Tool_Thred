"""Non-destructive image/meme/video compositing and reaction inserts."""
import json
import math
from pathlib import Path

from PIL import Image,ImageOps

IMAGES={'.png','.jpg','.jpeg','.webp','.bmp'}
VIDEOS={'.mp4','.mov','.mkv','.webm','.gif'}


def media_info(path):
    from .render import probe
    path=Path(path)
    if not path.is_file():raise ValueError('Không tìm thấy media: '+path.name)
    if path.suffix.lower() in IMAGES:
        with Image.open(path) as im:return {'image':True,'width':im.width,'height':im.height,'audio':False,'duration':0}
    if path.suffix.lower() not in VIDEOS:raise ValueError('Media cần PNG/JPG/WebP/BMP/GIF hoặc video MP4/MOV/MKV/WebM.')
    info=probe(path);v=next((s for s in info['streams'] if s['codec_type']=='video'),None)
    if not v:raise ValueError('Media không có hình ảnh.')
    return {'image':False,'width':v['width'],'height':v['height'],'audio':any(s['codec_type']=='audio' for s in info['streams']),'duration':float(info['format'].get('duration',0))}


def scene_timeline(source):
    p=Path(source);timeline=p.parent/(p.stem+'_project')/'timeline.json'
    if not timeline.exists():return []
    try:return json.loads(timeline.read_text(encoding='utf8'))
    except Exception:return []


def normalize(items,duration,timeline=None):
    result=[];timeline=timeline or []
    for order,item in enumerate(items):
        d=dict(item);d['path']=str(Path(d['path']).resolve());d['info']=media_info(d['path']);d['order']=order
        for field,default in [('start',0),('duration',3),('x',40),('y',850),('width',280),('opacity',1),('volume',.7),('offset',0)]:
            d[field]=float(d.get(field,default))
            if not math.isfinite(d[field]):raise ValueError('Thông số media phải là số hữu hạn.')
        d['scene']=int(d.get('scene',0));d['mode']=d.get('mode','overlay');d['audio']=bool(d.get('audio',False))
        if d['mode'] not in {'overlay','insert'}:raise ValueError('Chế độ media không hợp lệ.')
        if d['start']<0 or d['duration']<=0 or d['offset']<0:raise ValueError('Thời điểm và offset không âm, thời lượng phải lớn hơn 0.')
        if not 16<=d['width']<=1440 or not 0<=d['opacity']<=1 or not 0<=d['volume']<=2:raise ValueError('Chiều rộng 16–1440 px, độ hiện 0–1, âm lượng 0–2.')
        if d['scene']:
            if not 1<=d['scene']<=len(timeline):raise ValueError('Không có cảnh này. Video ngoài tool chọn Cảnh = 0.')
            scene=timeline[d['scene']-1]
            if d['start']>scene['duration'] or (d['mode']=='overlay' and d['start']+d['duration']>scene['duration']+.04):raise ValueError('Media vượt thời lượng cảnh đã chọn.')
            d['start']+=scene['start']
        if d['mode']=='insert' and d['start']>duration+.03:raise ValueError('Điểm chèn đoạn vượt độ dài video gốc.')
        if not d['info']['image']:
            if d['info']['duration']<=0:raise ValueError('Clip không có thời lượng hợp lệ.')
            d['offset']%=d['info']['duration']
        result.append(d)
    inserts=sorted((d for d in result if d['mode']=='insert'),key=lambda d:(d['start'],d['order']))
    total=duration+sum(d['duration'] for d in inserts)
    for d in result:
        if d['mode']=='overlay':
            # Scene-relative overlays follow the original scene after preceding reaction inserts.
            if d['scene']:d['start']+=sum(i['duration'] for i in inserts if i['start']<=d['start'])
            if d['start']+d['duration']>total+.04:raise ValueError('Lớp phủ vượt thời lượng video sau khi chèn. Giảm thời lượng hoặc đổi thời điểm.')
    return result,total


def _piece(source,output,offset,duration,width,height,image,keep_audio,cancel,volume=1):
    from .render import run
    cmd=['ffmpeg','-v','error','-y']
    if image:cmd+=['-loop','1','-framerate','30','-i',source]
    else:cmd+=['-stream_loop','-1','-ss',str(offset),'-i',source]
    if not keep_audio:cmd+=['-f','lavfi','-i','anullsrc=r=44100:cl=stereo']
    cmd+=['-vf',f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1','-map','0:v','-map','0:a' if keep_audio else '1:a','-af',f'apad,aresample=44100,volume={volume}','-t',str(duration),'-r','30','-c:v','libx264','-threads','4','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-ar','44100','-ac','2',output]
    run(cmd,cancel)


def edit_video(source,output,items,log=print,progress=lambda _:None,cancel=None,timeline=None):
    from .render import probe,run,Cancelled
    source=Path(source).resolve();output=Path(output).resolve()
    if source==output or output.exists():raise ValueError('Chỉnh sửa luôn xuất tệp mới; không ghi đè video gốc hoặc tệp đã tồn tại.')
    info=probe(source);v=next(s for s in info['streams'] if s['codec_type']=='video');width,height=v['width'],v['height'];duration=float(info['format']['duration'])
    if not items:raise ValueError('Chưa thêm meme, ảnh hoặc clip.')
    edits,total=normalize(items,duration,timeline if timeline is not None else scene_timeline(source))
    output.parent.mkdir(parents=True,exist_ok=True);work=output.parent/(output.stem+'_edit');work.mkdir(exist_ok=True)
    inserts=sorted((e for e in edits if e['mode']=='insert'),key=lambda e:(e['start'],e['order']));base=source
    if inserts:
        log('Đang chèn đoạn phản ứng và giữ toàn bộ nội dung video gốc…');parts=[];cursor=0
        original_audio=any(s['codec_type']=='audio' for s in info['streams'])
        def part(path,offset,length,image,audio,volume=1):
            if length<.01:return
            out=work/f'piece_{len(parts):03}.mp4';_piece(path,out,offset,length,width,height,image,audio,cancel,volume);parts.append(out)
        for e in inserts:
            if cancel and cancel.is_set():raise Cancelled('Đã hủy chỉnh sửa.')
            part(source,cursor,e['start']-cursor,False,original_audio);part(e['path'],e['offset'],e['duration'],e['info']['image'],e['audio'] and e['info']['audio'],e['volume']);cursor=e['start']
        part(source,cursor,duration-cursor,False,original_audio)
        concat=work/'concat.txt';concat.write_text('\n'.join("file '"+p.name+"'" for p in parts),encoding='utf8');base=work/'inserted.mp4'
        run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',concat,'-c','copy',base],cancel);progress(.45)
    if cancel and cancel.is_set():raise Cancelled('Đã hủy chỉnh sửa.')
    overlays=[e for e in edits if e['mode']=='overlay'];staging=work/'finished.mp4'
    if not overlays:
        import shutil
        shutil.copy2(base,staging)
    else:
        log(f'Đang ghép {len(overlays)} lớp meme / ảnh / video…')
        base_info=probe(base);final_duration=float(base_info['format']['duration']);cmd=['ffmpeg','-v','error','-y','-i',base];filters=[];audio_labels=[]
        for e in overlays:
            if e['info']['image']:cmd+=['-loop','1','-framerate','30','-i',e['path']]
            else:cmd+=['-stream_loop','-1','-ss',str(e['offset']),'-i',e['path']]
        if any(s['codec_type']=='audio' for s in base_info['streams']):filters.append('[0:a]aresample=44100[a0]')
        else:
            ai=len(overlays)+1;cmd+=['-f','lavfi','-i','anullsrc=r=44100:cl=stereo'];filters.append(f'[{ai}:a]anull[a0]')
        audio_labels.append('[a0]');previous='0:v'
        for i,e in enumerate(overlays,1):
            w=max(2,int(e['width']*width/720)//2*2);x=int(e['x']*width/720);y=int(e['y']*height/1280)
            filters.append(f'[{i}:v]scale={w}:-2,setsar=1,format=rgba,colorchannelmixer=aa={e["opacity"]},setpts=PTS-STARTPTS+{e["start"]}/TB[m{i}]')
            filters.append(f'[{previous}][m{i}]overlay={x}:{y}:enable=\'gte(t,{e["start"]})*lt(t,{e["start"]+e["duration"]})\':eof_action=pass:repeatlast=0[v{i}]');previous=f'v{i}'
            if e['audio'] and e['info']['audio']:
                delay=int(e['start']*1000)
                filters.append(f'[{i}:a]atrim=duration={e["duration"]},asetpts=PTS-STARTPTS,aresample=44100,volume={e["volume"]},adelay={delay}:all=1[a{i}]');audio_labels.append(f'[a{i}]')
        filters.append(''.join(audio_labels)+f'amix=inputs={len(audio_labels)}:duration=first:normalize=0,alimiter=limit=0.95[a]')
        cmd+=['-filter_complex_threads','2','-filter_complex',';'.join(filters),'-map',f'[{previous}]','-map','[a]','-t',str(final_duration),'-r','30','-c:v','libx264','-threads','4','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-ar','44100','-ac','2','-movflags','+faststart',staging]
        run(cmd,cancel)
    check=probe(staging)
    if abs(float(check['format']['duration'])-total)>.15+len(inserts)*.08:raise RuntimeError('Thời lượng sau chỉnh sửa không khớp. Chưa xuất tệp cuối.')
    if cancel and cancel.is_set():raise Cancelled('Đã hủy chỉnh sửa.')
    staging.replace(output);(work/'edit_manifest.json').write_text(json.dumps({'source':str(source),'edits':items,'duration':check['format']['duration']},ensure_ascii=False,indent=2),encoding='utf8')
    progress(1);log('Đã xuất bản chỉnh sửa: '+str(output));return output


def _frame(path,t,width,height,fit=False):
    import cv2
    path=Path(path)
    if path.suffix.lower() in IMAGES:
        with Image.open(path) as source:im=ImageOps.exif_transpose(source).convert('RGBA')
    else:
        cap=cv2.VideoCapture(str(path));cap.set(cv2.CAP_PROP_POS_MSEC,max(0,t)*1000);ok,frame=cap.read();cap.release()
        if not ok:raise ValueError('Không đọc được khung hình xem trước.')
        im=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)).convert('RGBA')
    if fit:
        fitted=ImageOps.contain(im,(width,height));bg=Image.new('RGBA',(width,height),'black');bg.alpha_composite(fitted,((width-fitted.width)//2,(height-fitted.height)//2));return bg
    return im


def preview_frame(source,items,t,timeline=None):
    from .render import probe
    info=probe(source);duration=float(info['format']['duration']);edits,total=normalize(items,duration,timeline if timeline is not None else scene_timeline(source));t=max(0,min(float(t),total-.04));cursor=0;out_cursor=0;chosen=None
    for e in sorted((e for e in edits if e['mode']=='insert'),key=lambda e:(e['start'],e['order'])):
        gap=e['start']-cursor
        if t<out_cursor+gap:chosen=(source,cursor+t-out_cursor);break
        out_cursor+=gap;cursor=e['start']
        if t<out_cursor+e['duration']:
            phase=0 if e['info']['image'] else (e['offset']+t-out_cursor)%e['info']['duration'];chosen=(e['path'],phase);break
        out_cursor+=e['duration']
    if chosen is None:chosen=(source,cursor+t-out_cursor)
    im=_frame(*chosen,720,1280,True)
    for e in edits:
        if e['mode']!='overlay' or not e['start']<=t<e['start']+e['duration']:continue
        phase=0 if e['info']['image'] else (e['offset']+t-e['start'])%e['info']['duration'];asset=_frame(e['path'],phase,720,1280)
        width=int(e['width'])//2*2;height=max(2,round(asset.height*width/asset.width/2)*2);asset=asset.resize((width,height))
        asset.putalpha(asset.getchannel('A').point(lambda a:round(a*e['opacity'])));im.alpha_composite(asset,(int(e['x']),int(e['y'])))
    return im,total
