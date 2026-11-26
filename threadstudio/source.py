import hashlib
import json
import re
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
import requests
from bs4 import BeautifulSoup
from .render import ROOT, Cancelled, probe

EXTRACT = r"""() => {
 const result=[], seen=new Set();
 const canonical = href => (href.match(/\/@[^/]+\/post\/[\w-]+/)||[])[0] || href;
 for(const a of document.querySelectorAll('a[href*="/post/"]')) {
  const href=a.getAttribute('href');
  if(seen.has(href) || !/\/@[^/]+\/post\//.test(href) || !a.querySelector('time')) continue;
  let el=a;
  while(el && !(el.querySelectorAll('button,[role="button"]').length>=4 && new Set(Array.from(el.querySelectorAll('a[href*="/post/"]')).map(x=>canonical(x.getAttribute('href')))).size===1)) el=el.parentElement;
  if(!el) continue;
  const content=Array.from(el.querySelectorAll('[data-pressable-container]')).length;
  const lines=Array.from(el.querySelectorAll('[dir="auto"]')).filter(x=> !x.querySelector('[dir="auto"]')).map(x=>x.innerText.trim()).filter(Boolean);
  const user=(href.match(/\/@([^/]+)/)||[])[1];
  const buttons=Array.from(el.querySelectorAll('button,[role="button"]')).map(x=>(x.getAttribute('aria-label')||x.querySelector('[aria-label]')?.getAttribute('aria-label')||x.querySelector('svg title')?.textContent||'')+' '+x.innerText);
  const text=lines.join('\n').split('\n').map(x=>x.trim()).filter(x=> x!==user && !/^(Thread|[\d.,KMB]+ views|\d+[smhdwy]|[\d.,]+[KMB]?|Translate|Author|· Author|AI content|Edited|Replying to.*)$/.test(x) && x.length>1).join('\n');
  const img=el.querySelector('img');
  let media=null;
  const vid=el.querySelector('video');
  if(vid){const vs=vid.currentSrc||vid.getAttribute('src')||(vid.querySelector('source')?vid.querySelector('source').getAttribute('src'):'')||'';if(/^https:/.test(vs))media={type:'video',url:vs};else if(vid.getAttribute('poster'))media={type:'image',url:vid.getAttribute('poster')};}
  if(!media){
   const imgs=Array.from(el.querySelectorAll('img')).filter(im=>{
    const a=im.closest('a');const href=a?a.getAttribute('href')||'':'';
    if(/\/media/.test(href))return true;
    if(/^\/@[^/]+\/?$/.test(href))return false;
    return (im.naturalWidth||0)>=320;
   });
   if(imgs.length)media={type:'image',url:imgs[0].src};
  }
  result.push({username:user,text, url:new URL(href,location.origin).href,date:a.innerText,avatar:img?.src||'',verified:!!el.querySelector('[aria-label="Verified"],svg[title="Verified"]'),stats:buttons.filter(x=>/^(Like|Comment|Repost|Share)/.test(x)),media});
  seen.add(href);
 }
 return result;
}"""


def validate_url(url):
    p = urlsplit(url.strip())
    match=re.fullmatch(r'(/@[^/]+/post/[\w-]+)(?:/media)?/?',p.path)
    if p.scheme != 'https' or p.hostname not in {'threads.com', 'www.threads.com', 'threads.net', 'www.threads.net'} or not match:
        raise ValueError('Nhập link bài đăng https://www.threads.com/@.../post/...')
    return 'https://www.threads.com' + match.group(1)


def metadata_post(html, url):
    soup=BeautifulSoup(html,'html.parser')
    meta={x.get('property'):x.get('content','') for x in soup.select('meta[property^="og:"]')}
    if not meta.get('og:description','').strip() or '/post/' not in meta.get('og:url',''):
        return None
    if re.search(r'/post/([\w-]+)',meta['og:url']).group(1) != re.search(r'/post/([\w-]+)',url).group(1):return None
    post={'username':re.search(r'/@([^/]+)',url).group(1),'text':meta['og:description'].strip(),'url':url,'date':'','avatar':'','stats':[],'verified':False}
    if meta.get('og:video'):post['media']={'type':'video','url':meta['og:video']}
    elif meta.get('og:image'):post['media']={'type':'image','url':meta['og:image']}
    return post


def attach_media(data, log=print):
    """Download post/comment media (image/video) to a local cache and record the file
    path on each post. Posts whose media cannot be downloaded keep no media and render
    with the normal gameplay background."""
    cache = ROOT / 'data' / 'post_media'; cache.mkdir(parents=True, exist_ok=True)
    for post in data.get('posts', []):
        media = post.get('media')
        if not media or not media.get('url'):
            continue
        if media.get('path') and Path(media['path']).is_file():
            continue
        ext = Path(urlsplit(media['url']).path).suffix.lower()
        if ext not in {'.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mov', '.webm'}:
            ext = '.mp4' if media.get('type') == 'video' else '.jpg'
        target = cache / (hashlib.sha1(media['url'].encode()).hexdigest()[:16] + ext)
        if not target.is_file():
            try:
                r = requests.get(media['url'], headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.threads.com/'}, timeout=25, stream=True)
                r.raise_for_status()
                size = 0
                with open(target, 'wb') as f:
                    for chunk in r.iter_content(262144):
                        size += len(chunk)
                        if size > 80 * 1024 * 1024:
                            raise ValueError('media too large')
                        f.write(chunk)
            except Exception:
                target.unlink(missing_ok=True)
                post.pop('media', None)
                continue
        try:
            has_video = any(st.get('codec_type') == 'video' and st.get('codec_name') not in {'png', 'mjpeg', 'bmp', 'webp', 'gif', 'tiff'} for st in probe(target).get('streams', []))  # ffprobe reports still images as video streams too
        except Exception:
            has_video = media.get('type') == 'video'
        if media.get('type') == 'video' and not has_video:
            target.unlink(missing_ok=True); post.pop('media', None); continue  # downloaded file is not really a video
        if media.get('type') != 'video' and has_video:
            media['type'] = 'video'
        media['path'] = str(target)
        log(f"Đã tải {media['type']} đính kèm của @{post['username']}.")
    return data

def _launch_context(p, headless=True, profile=None, viewport=None, log=print):
    """Persistent browser profile: Threads/TikTok cookies survive between runs, so a
    one-time manual login sticks. Tries Google Chrome, then Edge, then Playwright's
    bundled Chromium — installing that Chromium automatically (one-time download)
    when no system browser can be used, so the app never dies on a missing browser."""
    profile = Path(profile) if profile else ROOT / 'data' / 'browser_profile'
    profile.mkdir(parents=True, exist_ok=True)
    kw = {'viewport': viewport or {'width': 1280, 'height': 1000}, 'locale': 'en-US'}
    for channel in ('msedge', 'chrome'):  # Edge first (built into Windows), then Google Chrome
        try:
            return p.chromium.launch_persistent_context(str(profile), channel=channel, headless=headless, **kw)
        except Exception:
            continue
    try:
        return p.chromium.launch_persistent_context(str(profile), headless=headless, chromium_sandbox=False, **kw)
    except Exception:
        pass
    log('Đang tải trình duyệt tích hợp cho app (chỉ tải một lần, khoảng 150 MB)…')
    try:
        for pkg in ('chromium-headless-shell', 'chromium'):  # shell first (headless fetch), full build for visible windows
            subprocess.run([sys.executable, '-m', 'playwright', 'install', pkg], capture_output=True, timeout=900)
    except Exception:
        pass
    try:
        return p.chromium.launch_persistent_context(str(profile), headless=headless, chromium_sandbox=False, **kw)
    except Exception as e:
        raise RuntimeError('Không mở được trình duyệt nào (Chrome, Edge đều lỗi và trình duyệt tích hợp cũng không chạy được). Chi tiết: ' + str(e)[:200])


def open_login_browser(log=print):
    """Open a visible browser on the app's own profile so the user can log in to Threads once."""
    with sync_playwright() as p:
        ctx = _launch_context(p, headless=False)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto('https://www.threads.com/', wait_until='domcontentloaded', timeout=60000)
            log('Đã mở trình duyệt bằng hồ sơ riêng của app. Hãy đăng nhập Threads trong cửa sổ đó, xong thì đóng cửa sổ trình duyệt lại.')
            while ctx.pages:
                page.wait_for_timeout(600)
        except Exception:
            pass
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def fetch_thread(url, log=print, limit=30, cancel=None):
    url = validate_url(url)
    limit=max(0,min(200,int(limit)))
    fallback=None
    try:
        r=requests.get(url,headers={'User-Agent':'Mozilla/5.0'},timeout=18)
        if r.ok:fallback=metadata_post(r.text,url)
    except requests.RequestException:pass
    if cancel and cancel.is_set():raise Cancelled('Đã hủy lấy nội dung.')
    log('Đang mở Threads và lấy bài viết, bình luận công khai…')
    with sync_playwright() as p:
        browser = _launch_context(p, headless=True)
        try:
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            try:
                page.locator('a[href*="/post/"] time').first.wait_for(timeout=15000)
            except Exception:
                pass  # page may be slow or walled; the extraction loop below still tries
            posts, seen, stale = [], set(), 0
            for _ in range(12):
                if cancel and cancel.is_set():raise Cancelled('Đã hủy lấy nội dung.')
                found = page.evaluate(EXTRACT)
                old = len(posts)
                for post in found:
                    if post['url'] not in seen and post['text']:
                        seen.add(post['url']); posts.append(post)
                stale = stale + 1 if len(posts) == old else 0
                if stale >= 2 or len(posts) >= limit + 1:
                    break
                page.mouse.wheel(0, 850)
                page.wait_for_timeout(1200)
            primary = next((x for x in posts if urlsplit(x['url']).path.rstrip('/') == urlsplit(url).path.rstrip('/')), None)
            if primary:
                posts.remove(primary)
                if fallback:
                    primary['text']=fallback['text']
                    if fallback.get('media') and (not primary.get('media') or (fallback['media'].get('type')=='video' and primary['media'].get('type')!='video')):
                        primary['media']=fallback['media']
            elif fallback:primary=fallback
            else:raise RuntimeError('Chưa lấy được nội dung bài này. Threads có thể đang bắt đăng nhập trong trình duyệt của app — bấm nút "Đăng nhập Threads" ở tab Tạo hàng loạt, đăng nhập một lần trong cửa sổ trình duyệt hiện ra, rồi thử lại.')
            data = {'url': url, 'posts': [primary] + posts[:limit], 'notice': 'Chỉ lấy bình luận Threads hiển thị công khai; có thể ít hơn số đếm trên bài.'}
            attach_media(data, log)
            log(f"Đã lấy bài gốc và {len(data['posts']) - 1} bình luận công khai.")
            return data
        except Cancelled:raise
        except Exception:
            if not fallback:raise RuntimeError('Chưa lấy được nội dung bài này. Threads có thể đang bắt đăng nhập trong trình duyệt của app — bấm nút "Đăng nhập Threads" ở tab Tạo hàng loạt, đăng nhập một lần trong cửa sổ trình duyệt hiện ra, rồi thử lại.')
            log('Đã lấy bài gốc từ nội dung công khai dự phòng; chưa tải được bình luận. Có thể thử lại sau.')
            data={'url':url,'posts':[fallback],'notice':'Nội dung công khai dự phòng; chưa tải được bình luận.'}
            attach_media(data, log)
            return data
        finally:
            browser.close()


def save_project(data, path):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
