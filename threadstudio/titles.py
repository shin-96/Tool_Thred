"""Short display titles summarising what a post says, plus filename slugs."""
import re
import unicodedata

_JUNK_LINES = {'top', 'view activity', 'view all', 'see translation', 'đã dịch', 'ẩn bản dịch'}


def summarize_title(text, limit=66):
    """First meaningful words of the post, cut at a word boundary. This is the
    author's own opening, lightly cleaned — not a generated paraphrase."""
    lines = []
    for raw in (text or '').splitlines():
        line = ' '.join(raw.split())
        if line and line.lower() not in _JUNK_LINES:
            lines.append(line)
    flat = ' '.join(' '.join(lines).split())
    flat = re.sub(r'\s+([:,.!?…])', r'\1', flat).strip()
    if len(flat) <= limit:
        return flat
    cut = flat[:limit].rsplit(' ', 1)[0].rstrip(' ,;:·-')
    return cut + '…' if cut else flat[:limit]


def slugify_title(title, limit=48):
    slug = unicodedata.normalize('NFKD', title or '')
    slug = ''.join(c for c in slug if not unicodedata.combining(c))
    slug = slug.replace('đ', 'd').replace('Đ', 'D').lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
    if len(slug) > limit:
        slug = slug[:limit].rsplit('-', 1)[0].strip('-')
    return slug or 'video'
