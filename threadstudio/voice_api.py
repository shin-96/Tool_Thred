"""Pluggable TTS adapters. Credentials stay in DPAPI settings, outside job snapshots."""
import base64
import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlsplit,quote
from xml.sax.saxutils import escape,quoteattr

import requests

from .secrets import protect,unprotect

KINDS=['OpenAI / tương thích','ElevenLabs','Azure Speech','HTTP JSON tùy chỉnh']
DEFAULTS={KINDS[0]:{'endpoint':'https://api.openai.com/v1/audio/speech','model':'gpt-4o-mini-tts','voice':'coral','key_header':'Authorization','key_prefix':'Bearer '},KINDS[1]:{'endpoint':'https://api.elevenlabs.io/v1/text-to-speech/{voice}','model':'eleven_multilingual_v2','voice':'','key_header':'xi-api-key','key_prefix':''},KINDS[2]:{'endpoint':'https://southeastasia.tts.speech.microsoft.com/cognitiveservices/v1','model':'','voice':'vi-VN-HoaiMyNeural','key_header':'Ocp-Apim-Subscription-Key','key_prefix':''},KINDS[3]:{'endpoint':'https://your-provider.example/tts','model':'','voice':'','key_header':'Authorization','key_prefix':'Bearer '}}
BODY_DEFAULT={'text':'{text}','voice':'{voice}','model':'{model}'}


def validate_endpoint(url):
    p=urlsplit(url)
    if p.username or p.password or p.fragment:raise ValueError('Endpoint không được chứa tài khoản, mật khẩu hoặc fragment.')
    if p.scheme!='https' and not (p.scheme=='http' and p.hostname in {'localhost','127.0.0.1','::1'}):raise ValueError('Dùng HTTPS cho API; HTTP chỉ dùng với máy localhost.')
    if not p.hostname:raise ValueError('Endpoint API không hợp lệ.')
    return url


def public_profile(profile):
    return {k:v for k,v in profile.items() if k not in {'secret','api_key','token'}}


def save_profile(store,profile,key='',profile_id=None):
    profiles=store.get_setting('voice_apis',{});pid=profile_id or uuid.uuid4().hex
    p=public_profile(profile);p['id']=pid
    if not p.get('name','').strip():raise ValueError('Nhập tên cấu hình giọng đọc.')
    if p.get('kind') not in KINDS:raise ValueError('Loại API không hợp lệ.')
    validate_endpoint(p.get('endpoint','').replace('{voice}',quote(p.get('voice',''),safe='')))
    if not re.fullmatch(r'[A-Za-z0-9-]+',p.get('key_header','Authorization')):raise ValueError('Tên header API key không hợp lệ.')
    speed=float(p.get('speed',1));p['speed']=speed
    if not .25<=speed<=4:raise ValueError('Tốc độ API từ 0.25 đến 4.')
    if '\r' in p.get('key_prefix','') or '\n' in p.get('key_prefix',''):raise ValueError('Tiền tố key không hợp lệ.')
    if p['kind']==KINDS[3] and not isinstance(p.get('body',BODY_DEFAULT),dict):raise ValueError('Body tùy chỉnh phải là JSON object.')
    p['secret']=protect(key) if key else profiles.get(pid,{}).get('secret','')
    old=profiles.get(pid,{})
    if old.get('secret') and not key and any(p.get(k)!=old.get(k) for k in ['endpoint','key_header','key_prefix']):raise ValueError('Khi đổi địa chỉ/xác thực, nhập lại API key cho đích mới.')
    profiles[pid]=p;store.setting('voice_apis',profiles);return pid


def replace_fields(obj,values):
    if isinstance(obj,dict):return {k:replace_fields(v,values) for k,v in obj.items()}
    if isinstance(obj,list):return [replace_fields(v,values) for v in obj]
    if isinstance(obj,str):
        obj=re.sub(r'\{(text|voice|model|speed)\}',lambda match:str(values[match.group(1)]),obj)
    return obj


def request_audio(profile,key,text,session=None,cancel=None):
    from .render import Cancelled
    if cancel and cancel.is_set():raise Cancelled('Đã hủy yêu cầu giọng đọc.')
    s=session or requests.Session();endpoint=validate_endpoint(profile['endpoint'].replace('{voice}',quote(profile.get('voice',''),safe='')))
    headers={'Content-Type':'application/json'}
    if key:headers[profile.get('key_header','Authorization')]=profile.get('key_prefix','Bearer ')+key
    voice=profile.get('voice','');model=profile.get('model','');kind=profile['kind']
    options={'timeout':(15,120),'allow_redirects':False,'headers':headers}
    if kind==KINDS[0]:options['json']={'model':model,'voice':voice,'input':text,'response_format':'mp3','speed':float(profile.get('speed',1))}
    elif kind==KINDS[1]:options['json']={'text':text,'model_id':model,'voice_settings':{'speed':float(profile.get('speed',1))}}
    elif kind==KINDS[2]:
        headers.update({'Content-Type':'application/ssml+xml','X-Microsoft-OutputFormat':'audio-24khz-96kbitrate-mono-mp3','User-Agent':'ThreadsStudioPro'})
        locale='-'.join(voice.split('-')[:2]) or 'vi-VN'
        options['data']=(f'<speak version="1.0" xml:lang={quoteattr(locale)}><voice name={quoteattr(voice)}><prosody rate="{round((float(profile.get("speed",1))-1)*100):+}%">{escape(text)}</prosody></voice></speak>').encode('utf8')
    else:options['json']=replace_fields(profile.get('body',BODY_DEFAULT),{'text':text,'voice':voice,'model':model,'speed':profile.get('speed',1)})
    try:r=s.post(endpoint,**options)
    except requests.RequestException:raise RuntimeError('Kết nối TTS API bị gián đoạn. Không tự gửi lại yêu cầu có thể tính phí; hãy kiểm tra rồi Thử lại.') from None
    if r.status_code!=200:raise RuntimeError(f'TTS API trả HTTP {r.status_code}. Kiểm tra endpoint, key, quyền truy cập và hạn mức.')
    response=profile.get('response','audio') if kind==KINDS[3] else 'audio'
    if response=='audio':return r.content
    try:
        value=r.json()
        for part in profile.get('response_path','audio').split('.'):
            value=value[int(part)] if isinstance(value,list) else value[part]
        if response=='base64':return base64.b64decode(value.split(',',1)[-1],validate=True)
        if response!='url':raise ValueError()
        url=validate_endpoint(str(value))
    except Exception:raise RuntimeError('Không tìm thấy âm thanh tại đường dẫn JSON đã cấu hình.') from None
    # Signed audio URLs receive no API key, even when they use another host.
    try:audio=s.get(url,timeout=(15,120),allow_redirects=False)
    except requests.RequestException:raise RuntimeError('Chưa tải được URL âm thanh trả về. Không tự tạo lại giọng để tránh tính phí lần nữa.') from None
    if audio.status_code!=200:raise RuntimeError('URL âm thanh chưa sẵn sàng hoặc đã hết hạn. API bất đồng bộ cần trả URL đã sẵn sàng.')
    return audio.content


def synthesize_api(text,profile,audio,log=print,cancel=None,store=None,session=None):
    from .render import ROOT,probe,Cancelled,run
    from .store import Store
    store=store or Store();stored=store.get_setting('voice_apis',{}).get(profile['id'])
    if not stored:raise ValueError('Cấu hình TTS API đã bị gỡ. Chọn lại giọng trước khi chạy.')
    # Bind credentials to the configured destination; editing an endpoint cannot redirect an old key.
    for field in ['endpoint','key_header','key_prefix','kind']:
        if profile.get(field)!=stored.get(field):raise ValueError('Địa chỉ / xác thực TTS API đã thay đổi. Sửa tác vụ và chọn lại cấu hình.')
    key=unprotect(stored['secret']) if stored.get('secret') else ''
    cache=ROOT/'assets'/'speech_cache';cache.mkdir(exist_ok=True)
    identity='canonical-mp3-v1'+json.dumps(public_profile(profile),sort_keys=True,ensure_ascii=False)+text
    target=cache/('api_'+hashlib.sha256(identity.encode()).hexdigest()+'.audio')
    if target.exists():
        try:probe(target);shutil.copy2(target,audio);return 'api:'+profile['name']
        except Exception:pass
    log('Đang tạo giọng từ API: '+profile['name'])
    content=request_audio(profile,key,text,session,cancel)
    if cancel and cancel.is_set():raise Cancelled('Đã hủy giọng API sau khi nhận phản hồi.')
    tmp=target.with_suffix('.'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(content)
    try:
        info=probe(tmp)
        if not any(s['codec_type']=='audio' for s in info['streams']) or float(info['format'].get('duration',0))<=0:raise ValueError()
        encoded=target.with_suffix('.'+uuid.uuid4().hex+'.mp3')
        try:
            run(['ffmpeg','-v','error','-y','-i',tmp,'-vn','-c:a','libmp3lame','-ar','44100','-ac','2','-q:a','3',encoded],cancel)
            encoded.replace(target);shutil.copy2(target,audio)
        finally:encoded.unlink(missing_ok=True);tmp.unlink(missing_ok=True)
    except Cancelled:
        tmp.unlink(missing_ok=True);raise
    except Exception:
        tmp.unlink(missing_ok=True);raise RuntimeError('API không trả tệp âm thanh hợp lệ. Kiểm tra kiểu phản hồi; chưa ghép video.') from None
    return 'api:'+profile['name']
