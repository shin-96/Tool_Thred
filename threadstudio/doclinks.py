"""Read Threads post links from a Google Doc shared as "anyone with the link can
view". The doc is fetched through Google's export-as-text endpoint, so no Google
login is needed on this machine — the doc only has to be link-shared. The doc is
expected to contain nothing but Threads links, one per line."""
import re

import requests

_DOC_ID = re.compile(r'/document/d/([a-zA-Z0-9_-]{20,})')
_BARE_ID = re.compile(r'[a-zA-Z0-9_-]{20,}')
_POST = re.compile(r'https?://(?:www\.)?threads\.(?:com|net)/@[^\s/]+/post/[A-Za-z0-9_-]+')


def doc_id(value):
    """Accept a full Google Docs URL or a bare document id."""
    value = (value or '').strip()
    m = _DOC_ID.search(value)
    if m:
        return m.group(1)
    if _BARE_ID.fullmatch(value):
        return value
    raise ValueError('Không nhận ra link Google Doc. Dán link dạng https://docs.google.com/document/d/<id>/edit')


def fetch_doc_text(value):
    did = doc_id(value)
    r = requests.get(f'https://docs.google.com/document/d/{did}/export?format=txt',
                     headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
    if r.status_code in (401, 403):
        raise ValueError('Không đọc được Doc. Mở Doc, bấm Chia sẻ và chọn "Bất kỳ ai có đường liên kết — Người xem" rồi thử lại.')
    r.raise_for_status()
    return r.text


def extract_links(text):
    """All Threads post links in the text, host normalized to www.threads.com,
    deduplicated, in document order."""
    out, seen = [], set()
    for m in _POST.finditer(text or ''):
        url = re.sub(r'^https?://(?:www\.)?threads\.(?:com|net)', 'https://www.threads.com', m.group(0))
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out
