"""Non-destructive image/meme/video compositing and reaction inserts."""
import json
import math
from pathlib import Path

from PIL import Image,ImageOps

IMAGES={'.png','.jpg','.jpeg','.webp','.bmp'}
VIDEOS={'.mp4','.mov','.mkv','.webm','.gif'}
AUDIOS={'.mp3','.wav','.m4a','.aac','.ogg','.flac','.opus'}


def media_info(path):
    from .render import probe
    path=Path(path)
    if not path.is_file():raise ValueError('Không tìm thấy media: '+path.name)
    if path.suffix.lower() in IMAGES:
        with Image.open(path) as im:return {'image':True,'width':im.width,'height':im.height,'audio':False,'duration':0}
    if path.suffix.lower() in AUDIOS:
        info=probe(path)
        if not any(st['codec_type']=='audio' for st in info['streams']):raise ValueError('Tệp âm thanh không hợp lệ.')
        return {'image':False,'audio_only':True,'width':0,'height':0,'audio':True,'duration':float(info['format'].get('duration',0))}
    if path.suffix.lower() not in VIDEOS:raise ValueError('Media cần PNG/JPG/WebP/BMP/GIF, video MP4/MOV/MKV/WebM hoặc âm thanh MP3/WAV/M4A/OGG.')
    info=probe(path);v=next((s for s in info['streams'] if s['codec_type']=='video'),None)
    if not v:raise ValueError('Media không có hình ảnh.')
    return {'image':False,'width':v['width'],'height':v['height'],'audio':any(s['codec_type']=='audio' for s in info['streams']),'duration':float(info['format'].get('duration',0))}


def scene_timeline(source):
    p=Path(source);timeline=p.parent/(p.stem+'_project')/'timeline.json'
    if not timeline.exists():return []
    try:return json.loads(timeline.read_text(encoding='utf8'))
    except Exception:return []



KF_PROPS=('x','y','width','opacity','rotation')

def _fade_factor(item,t):
    f=1.0;dur=float(item.get('duration',0))
    fi=float(item.get('fade_in',0) or 0);fo=float(item.get('fade_out',0) or 0)
    if fi>0 and t<fi:f=min(f,t/fi)
    if fo>0 and dur-t<fo:f=min(f,max(0.0,(dur-t)/fo))
    return f

def keyframe_state(item,t):
    """Interpolated x/y/width/opacity/rotation at local time t (seconds into the item)."""
    base={k:float(item.get(k,{'x':40,'y':850,'width':280,'opacity':1,'rotation':0}[k])) for k in KF_PROPS}
    kfs=sorted(item.get('keyframes') or [],key=lambda k:k['t'])
    if kfs:
        if t<=kfs[0]['t']:state={**base,**{k:float(kfs[0][k]) for k in KF_PROPS if k in kfs[0]}}
        elif t>=kfs[-1]['t']:state={**base,**{k:float(kfs[-1][k]) for k in KF_PROPS if k in kfs[-1]}}
        else:
            state=dict(base)
            for a,b in zip(kfs,kfs[1:]):
                if a['t']<=t<=b['t']:
                    r=0 if b['t']==a['t'] else (t-a['t'])/(b['t']-a['t'])
                    for k in KF_PROPS:
                        va=float(a.get(k,base[k]));vb=float(b.get(k,base[k]));state[k]=va+(vb-va)*r
                    break
    else:state=base
    state['opacity']=max(0.0,min(1.0,state['opacity']*_fade_factor(item,t)))
    return state

def chroma_key(im,chroma):
    """Make pixels near the key colour transparent (numpy); slight green despill."""
    import numpy as np
    key=chroma.get('color','#00ff00').lstrip('#');kr,kg,kb=(int(key[i:i+2],16) for i in (0,2,4))
    sim=float(chroma.get('similarity',0.35));blend=max(0.01,float(chroma.get('blend',0.15)))
    arr=np.asarray(im).astype(np.float32);rgb=arr[...,:3]
    dist=np.sqrt(((rgb-np.array([kr,kg,kb],dtype=np.float32))**2).sum(axis=2))/441.7
    factor=np.clip((dist-sim)/blend,0,1)
    arr[...,3]*=factor
    if (kr,kg,kb)==(0,255,0):  # despill only where the key colour was removed
        strong=factor<0.5;arr[...,1]=np.where(strong,np.minimum(arr[...,1],np.maximum(arr[...,0],arr[...,2])),arr[...,1])
    return Image.fromarray(arr.astype('uint8'),'RGBA')

def place_asset(canvas,asset,state):
    """Resize/rotate/fade asset per state and composite; x/y = top-left of the unrotated box."""
    width=max(2,int(state['width'])//2*2);height=max(2,round(asset.height*width/asset.width/2)*2)
    asset=asset.resize((width,height))
    rot=float(state.get('rotation',0) or 0)
    if rot:asset=asset.rotate(-rot,expand=True,resample=Image.BILINEAR)
    if state['opacity']<1:asset.putalpha(asset.getchannel('A').point(lambda a:round(a*state['opacity'])))
    cx=state['x']+width/2;cy=state['y']+height/2
    canvas.alpha_composite(asset,(round(cx-asset.width/2),round(cy-asset.height/2)))
    return canvas


def normalize(items,duration,timeline=None):
    result=[];timeline=timeline or []
    for order,item in enumerate(items):
        d=dict(item);d['path']=str(Path(d['path']).resolve());d['info']=media_info(d['path']);d['order']=order
        for field,default in [('start',0),('duration',3),('x',40),('y',850),('width',280),('opacity',1),('volume',.7),('offset',0),('rotation',0),('fade_in',0),('fade_out',0)]:
            d[field]=float(d.get(field,default))
            if not math.isfinite(d[field]):raise ValueError('Thông số media phải là số hữu hạn.')
        d['scene']=int(d.get('scene',0));d['mode']=d.get('mode','overlay');d['audio']=bool(d.get('audio',False))
        if d['info'].get('audio_only'):d['mode']='audio'
        if d['mode'] not in {'overlay','insert','audio'}:raise ValueError('Chế độ media không hợp lệ.')
        if d['start']<0 or d['duration']<=0 or d['offset']<0:raise ValueError('Thời điểm và offset không âm, thời lượng phải lớn hơn 0.')
        if not 0<=d['volume']<=2:raise ValueError('Âm lượng 0–2.')
        if d['mode']!='audio' and (not 16<=d['width']<=1440 or not 0<=d['opacity']<=1):raise ValueError('Chiều rộng 16–1440 px, độ hiện 0–1.')
        if not -360<=d['rotation']<=360:raise ValueError('Góc xoay -360–360.')
        if d['fade_in']<0 or d['fade_out']<0 or d['fade_in']+d['fade_out']>d['duration']+.04:raise ValueError('Fade in/out không âm và tổng không vượt thời lượng lớp.')
        kfs=[]
        for kf in d.get('keyframes') or []:
            k={'t':float(kf['t'])}
            if not 0<=k['t']<=d['duration']+.001:raise ValueError('Keyframe phải nằm trong thời lượng lớp media.')
            for prop in KF_PROPS:
                if prop in kf:
                    k[prop]=float(kf[prop])
                    if not math.isfinite(k[prop]):raise ValueError('Keyframe phải là số hữu hạn.')
            if 'width' in k and not 16<=k['width']<=1440:raise ValueError('Keyframe: chiều rộng 16–1440 px.')
            if 'opacity' in k and not 0<=k['opacity']<=1:raise ValueError('Keyframe: độ hiện 0–1.')
            kfs.append(k)
        d['keyframes']=sorted(kfs,key=lambda k:k['t'])
        ch=d.get('chroma')
        if ch:
            col=str(ch.get('color','#00ff00'))
            if len(col)!=7 or col[0]!='#':raise ValueError('Màu tách nền dạng #RRGGBB.')
            int(col[1:],16)
            d['chroma']={'color':col,'similarity':min(.95,max(0.,float(ch.get('similarity',.35)))),'blend':min(.9,max(.01,float(ch.get('blend',.15))))}
        else:d['chroma']=None
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
        if d['mode'] in ('overlay','audio'):
            # Scene-relative overlays follow the original scene after preceding reaction inserts.
            if d['scene']:d['start']+=sum(i['duration'] for i in inserts if i['start']<=d['start'])
            if d['start']+d['duration']>total+.04:raise ValueError('Lớp phủ vượt thời lượng video sau khi chèn. Giảm thời lượng hoặc đổi thời điểm.')
    return result,total


def is_fx(item):
    return bool(item.get('keyframes') or item.get('chroma') or item.get('fade_in') or item.get('fade_out') or item.get('rotation'))


def _bake_fx(item,base_size,work,cancel=None):
    """Render an animated/chroma overlay as a full-frame transparent clip (qtrle .mov).

    shortcut: per-frame Python compositing at 30 fps — precise for keyframes/chroma/rotation,
    but slower than the static ffmpeg path; only fx overlays take this route.
    """
    from .render import run
    width,height=base_size;scale=width/720
    frames=work/f"fx_{item['order']:02d}_frames";frames.mkdir(exist_ok=True)
    n=max(1,round(item['duration']*30))
    for i in range(n):
        if cancel and cancel.is_set():
            from .render import Cancelled
            raise Cancelled('Đã hủy chỉnh sửa.')
        tl=i/30;state=keyframe_state(item,tl)
        state={**state,'x':state['x']*scale,'y':state['y']*height/1280,'width':state['width']*scale}
        phase=0 if item['info']['image'] else (item['offset']+tl)%item['info']['duration']
        asset=_frame(item['path'],phase,720,1280)
        if item.get('chroma'):asset=chroma_key(asset,item['chroma'])
        canvas=Image.new('RGBA',(width,height),(0,0,0,0))
        place_asset(canvas,asset,state);canvas.save(frames/f'f{i:04d}.png')
    out=work/f"fx_{item['order']:02d}.mov"
    run(['ffmpeg','-v','error','-y','-framerate','30','-i',str(frames/'f%04d.png'),'-c:v','qtrle','-pix_fmt','argb',str(out)],cancel)
    return out


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
    overlays=[e for e in edits if e['mode']=='overlay'];audios=[e for e in edits if e['mode']=='audio'];staging=work/'finished.mp4'
    if not overlays and not audios:
        import shutil
        shutil.copy2(base,staging)
    else:
        for e in overlays:
            if is_fx(e):e['_baked']=str(_bake_fx(e,(width,height),work,cancel))
        log(f'Đang ghép {len(overlays)} lớp meme / ảnh / video và {len(audios)} track âm thanh…')
        base_info=probe(base);final_duration=float(base_info['format']['duration']);cmd=['ffmpeg','-v','error','-y','-i',base];filters=[];audio_labels=[]
        for e in overlays:
            if e.get('_baked'):cmd+=['-i',e['_baked']]
            elif e['info']['image']:cmd+=['-loop','1','-framerate','30','-i',e['path']]
            else:cmd+=['-stream_loop','-1','-ss',str(e['offset']),'-i',e['path']]
        au_start=len(overlays)+1
        for e in audios:cmd+=['-stream_loop','-1','-ss',str(e['offset']),'-i',e['path']]
        baked_audio=[e for e in overlays if e.get('_baked') and e['audio'] and e['info']['audio']]
        ba_start=au_start+len(audios)
        for e in baked_audio:cmd+=['-stream_loop','-1','-ss',str(e['offset']),'-i',e['path']]
        if any(s['codec_type']=='audio' for s in base_info['streams']):filters.append('[0:a]aresample=44100[a0]')
        else:
            ai=ba_start+len(baked_audio);cmd+=['-f','lavfi','-i','anullsrc=r=44100:cl=stereo'];filters.append(f'[{ai}:a]anull[a0]')
        audio_labels.append('[a0]');previous='0:v'
        for i,e in enumerate(overlays,1):
            if e.get('_baked'):
                filters.append(f'[{i}:v]format=rgba,setpts=PTS-STARTPTS+{e["start"]}/TB[m{i}]')
                filters.append(f'[{previous}][m{i}]overlay=0:0:enable=\'gte(t,{e["start"]})*lt(t,{e["start"]+e["duration"]})\':eof_action=pass:repeatlast=0[v{i}]');previous=f'v{i}'
                continue
            w=max(2,int(e['width']*width/720)//2*2);x=int(e['x']*width/720);y=int(e['y']*height/1280)
            filters.append(f'[{i}:v]scale={w}:-2,setsar=1,format=rgba,colorchannelmixer=aa={e["opacity"]},setpts=PTS-STARTPTS+{e["start"]}/TB[m{i}]')
            filters.append(f'[{previous}][m{i}]overlay={x}:{y}:enable=\'gte(t,{e["start"]})*lt(t,{e["start"]+e["duration"]})\':eof_action=pass:repeatlast=0[v{i}]');previous=f'v{i}'
            if e['audio'] and e['info']['audio']:
                delay=int(e['start']*1000)
                filters.append(f'[{i}:a]atrim=duration={e["duration"]},asetpts=PTS-STARTPTS,aresample=44100,volume={e["volume"]},adelay={delay}:all=1[a{i}]');audio_labels.append(f'[a{i}]')
        for j,e in enumerate(baked_audio):
            idx=ba_start+j;delay=int(e['start']*1000)
            filters.append(f'[{idx}:a]atrim=duration={e["duration"]},asetpts=PTS-STARTPTS,aresample=44100,volume={e["volume"]},adelay={delay}:all=1[ba{j}]');audio_labels.append(f'[ba{j}]')
        for j,e in enumerate(audios):
            idx=au_start+j;delay=int(e['start']*1000);chain=f'[{idx}:a]atrim=duration={e["duration"]},asetpts=PTS-STARTPTS,aresample=44100,volume={e["volume"]}'
            if e['fade_in']>0:chain+=f',afade=t=in:st=0:d={e["fade_in"]}'
            if e['fade_out']>0:chain+=f',afade=t=out:st={max(0,e["duration"]-e["fade_out"])}:d={e["fade_out"]}'
            filters.append(chain+f',adelay={delay}:all=1[au{j}]');audio_labels.append(f'[au{j}]')
        filters.append(''.join(audio_labels)+f'amix=inputs={len(audio_labels)}:duration=first:normalize=0,alimiter=limit=0.95[a]')
        cmd+=['-filter_complex_threads','2','-filter_complex',';'.join(filters),'-map',f'[{previous}]','-map','[a]','-t',str(final_duration),'-r','30','-c:v','libx264','-threads','4','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-ar','44100','-ac','2','-movflags','+faststart',staging]
        run(cmd,cancel)
    check=probe(staging)
    if abs(float(check['format']['duration'])-total)>.15+len(inserts)*.08:raise RuntimeError('Thời lượng sau chỉnh sửa không khớp. Chưa xuất tệp cuối.')
    if cancel and cancel.is_set():raise Cancelled('Đã hủy chỉnh sửa.')
    staging.replace(output);(work/'edit_manifest.json').write_text(json.dumps({'source':str(source),'edits':items,'duration':check['format']['duration']},ensure_ascii=False,indent=2),encoding='utf8')
    progress(1);log('Đã xuất bản chỉnh sửa: '+str(output));return output


def mix_preview_audio(source,items,output):
    """Audio-only mix for editor preview playback: base sound + audio tracks + clip sound.
    Insert time-shifts are not applied (the inserted clip's sound plays at its start point
    over the base), which is close enough to judge how an edit sounds. Returns False when
    there is nothing audible."""
    from .render import probe, run
    info=probe(source);total=float(info['format'].get('duration',0));edits,_=normalize(items,total)
    cmd=['ffmpeg','-v','error','-y','-i',str(source)];filters=[];labels=[]
    if any(s['codec_type']=='audio' for s in info['streams']):
        filters.append('[0:a]aresample=44100[a0]');labels.append('[a0]')
    idx=0
    for e in edits:
        audible=e['mode']=='audio' or (e['audio'] and e['info'].get('audio'))
        if not audible:continue
        idx+=1;cmd+=['-stream_loop','-1','-ss',str(e['offset']),'-i',e['path']]
        chain=f'[{idx}:a]atrim=duration={e["duration"]},asetpts=PTS-STARTPTS,aresample=44100,volume={e["volume"]}'
        if e['mode']=='audio':
            if e['fade_in']>0:chain+=f',afade=t=in:st=0:d={e["fade_in"]}'
            if e['fade_out']>0:chain+=f',afade=t=out:st={max(0,e["duration"]-e["fade_out"])}:d={e["fade_out"]}'
        filters.append(chain+f',adelay={int(e["start"]*1000)}:all=1[au{idx}]');labels.append(f'[au{idx}]')
    if not labels:return False
    filters.append(''.join(labels)+f'amix=inputs={len(labels)}:duration=first:normalize=0,alimiter=limit=0.95[a]')
    cmd+=['-filter_complex',';'.join(filters),'-map','[a]','-t',str(total),'-ar','44100','-ac','2',str(output)]
    run(cmd);return True


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
        if e.get('chroma'):asset=chroma_key(asset,e['chroma'])
        place_asset(im,asset,keyframe_state(e,t-e['start']))
    return im,total
