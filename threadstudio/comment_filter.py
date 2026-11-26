"""Pick funny replies and drop advertising / product-link seeding comments.

Heuristic and editable: a reply is an ad when it carries a shopping link,
a phone/Zalo contact, or sales phrasing. Funny ranking prefers replies the
audience already rewarded (Like count scraped in post['stats']) plus laugh
markers in the text itself.
"""
import re

AD_WORDS = [
    'shopee', 'lazada', 'tiki.vn', 'sendo', 'affiliate', 'tiếp thị liên kết',
    'link bio', 'link ở bio', 'link trong bio', 'mua tại', 'mua ngay', 'đặt hàng',
    'check ib', 'check inbox', 'ib mình', 'inbox mình', 'nhắn tin cho mình',
    'nhắn mình để', 'zalo', 'giá chỉ', 'chỉ từ', 'giảm giá', 'freeship',
    'free ship', 'ship cod', 'tuyển ctv', 'tuyển cộng tác viên', 'kiếm tiền tại nhà',
    'việc nhẹ lương cao', 'thu nhập thụ động', 'sản phẩm chính hãng', 'chính hãng 100%',
    'bảo hành', 'tư vấn miễn phí', 'đăng ký ngay', 'ưu đãi hôm nay', 'số lượng có hạn',
    'nhanh tay', 'chốt đơn', 'lên đơn', 'sỉ lẻ', 'giá sỉ', 'cam kết hoàn tiền',
]
AD_PATTERNS = [
    re.compile(r'https?://|www\.|\b[\w-]+\.(com|vn|net|shop|store|io|me|link|xyz)\b', re.I),
    re.compile(r'\b0\d{9}\b'),                       # phone numbers
    re.compile(r'\b(shp\.ee|bit\.ly|shorten|rutgon)\b', re.I),
    re.compile(r'\b\d{2,3}[kK]\s*(?:đ|vnd|đồng)?\s*(?:/|món|cái|sp|sản phẩm)'),  # price tags like 199k/sp
]
LAUGH_EMOJI = '😂🤣😆😹'
LAUGH_WORDS = ['haha', 'hihi', 'hehe', 'cười', '=))', ':))', 'kkk', 'khà khà', 'cười ẻ', 'cười xỉu', 'xỉu']


def is_ad(text):
    low = ' ' + (text or '').lower() + ' '
    if any(p.search(text or '') for p in AD_PATTERNS):
        return True
    return any(w in low for w in AD_WORDS)


def parse_likes(post):
    for s in post.get('stats') or []:
        m = re.match(r'\s*Like\s+([\d.,]+)\s*([KMB])?', str(s), re.I)
        if m:
            n = float(m.group(1).replace(',', ''))
            return n * {'K': 1e3, 'M': 1e6, 'B': 1e9}.get((m.group(2) or '').upper(), 1)
    return 0.0


def funny_score(post):
    text = post.get('text', '') or ''
    score = parse_likes(post)
    score += 25 * sum(text.count(e) for e in LAUGH_EMOJI)
    low = text.lower()
    score += 12 * sum(low.count(w) for w in LAUGH_WORDS if w.isalpha())
    score += 6 * (text.count('=))') + text.count(':))'))
    words = len(text.split())
    if 4 <= words <= 60:
        score += 10
    elif words < 3:
        score -= 15                      # one-word replies rarely carry a joke
    if len(text) > 4 and sum(c.isupper() for c in text) / max(1, sum(c.isalpha() for c in text)) > 0.7:
        score -= 10                      # shouting caps
    score += min(10, text.count('!') * 2)
    return score


def select_posts(posts, max_posts, funny_only=False, log=None):
    """First post is always the main post; the rest are replies."""
    posts = list(posts or [])
    if not funny_only or len(posts) <= 1:
        return posts[:int(max_posts)]
    replies = posts[1:]
    kept = [p for p in replies if not is_ad(p.get('text', ''))]
    dropped = len(replies) - len(kept)
    kept.sort(key=funny_score, reverse=True)
    if log and dropped:
        log(f'Đã loại {dropped} bình luận quảng cáo / link sản phẩm; chọn {min(len(kept), max(0, int(max_posts) - 1))} bình luận hài nhất trong {len(kept)} bình luận sạch.')
    return [posts[0]] + kept[:max(0, int(max_posts) - 1)]
