import json
import re
import threading
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
import requests
from bs4 import BeautifulSoup
from .render import Cancelled

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
  result.push({username:user,text, url:new URL(href,location.origin).href,date:a.innerText,avatar:img?.src||'',verified:!!el.querySelector('[aria-label="Verified"],svg[title="Verified"]'),stats:buttons.filter(x=>/^(Like|Comment|Repost|Share)/.test(x))});
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
    return {'username':re.search(r'/@([^/]+)',url).group(1),'text':meta['og:description'].strip(),'url':url,'date':'','avatar':'','stats':[],'verified':False}


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
        try:
            browser = p.chromium.launch(channel='msedge', headless=True,chromium_sandbox=True)
        except Exception:
            browser = p.chromium.launch(headless=True,chromium_sandbox=False)  # fallback when Edge is absent
        try:
            page = browser.new_page(viewport={'width': 1280, 'height': 1000}, locale='en-US')
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            page.locator('a[href*="/post/"] time').first.wait_for(timeout=25000)
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
                if fallback:primary['text']=fallback['text']
            elif fallback:primary=fallback
            else:raise RuntimeError('Chưa lấy được nội dung bài này. Kiểm tra link, thử lại, hoặc nhập nội dung trong cửa sổ Sửa bài viết. Threads có thể yêu cầu đăng nhập.')
            data = {'url': url, 'posts': [primary] + posts[:limit], 'notice': 'Chỉ lấy bình luận Threads hiển thị công khai; có thể ít hơn số đếm trên bài.'}
            log(f"Đã lấy bài gốc và {len(data['posts']) - 1} bình luận công khai.")
            return data
        except Cancelled:raise
        except Exception:
            if not fallback:raise
            log('Đã lấy bài gốc từ nội dung công khai dự phòng; chưa tải được bình luận. Có thể thử lại sau.')
            return {'url':url,'posts':[fallback],'notice':'Nội dung công khai dự phòng; chưa tải được bình luận.'}
        finally:
            browser.close()


def save_project(data, path):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
